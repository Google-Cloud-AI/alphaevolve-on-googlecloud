# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deterministic nickname generation and resolution for AlphaEvolve resources.

Every experiment and program gets a prefixed two-word nickname
(e.g., "exp-brave-otter", "prog-swift-panda") generated from a hash
of its resource name. The prefix disambiguates resource types:

  - ``exp-`` for experiments (resource names containing
    ``alphaEvolveExperiments``)
  - ``prog-`` for programs (resource names containing
    ``alphaEvolvePrograms``)

Nicknames are deterministic: same resource name → same nickname, always.
"""

from __future__ import annotations

import contextlib
import hashlib
import random
import typing

import coolname
import filelock

from . import config

# Prefixes for resource types.
_EXPERIMENT_PREFIX = "exp-"
_PROGRAM_PREFIX = "prog-"


def _detect_resource_type(resource_name: str) -> str:
  """Returns the prefix for a resource name based on its type.

  Args:
    resource_name: Full GCP resource path.

  Returns:
    "exp-" for experiments, "prog-" for programs, "" for unknown.
  """
  if "alphaEvolvePrograms" in resource_name:
    return _PROGRAM_PREFIX
  if "alphaEvolveExperiments" in resource_name:
    return _EXPERIMENT_PREFIX
  return ""


def _generate_slug(resource_name: str) -> str:
  """Generates a deterministic two-word slug from a resource name.

  Args:
    resource_name: The full GCP resource path name to seed from.

  Returns:
    A hyphenated two-word slug (no prefix).
  """
  digest = hashlib.sha256(resource_name.encode()).digest()
  seed = int.from_bytes(digest[:8], "big")
  rng = random.Random(seed)
  coolname.replace_random(rng)
  slug = coolname.generate_slug(2)
  coolname.replace_random(random.Random())
  return slug


def generate_nickname(resource_name: str) -> str:
  """Generates a deterministic prefixed nickname from a resource name.

  Uses SHA-256 of the resource name as a seed for coolname's RNG,
  ensuring the same resource always gets the same nickname.

  Args:
    resource_name: The full GCP resource path name to seed from.

  Returns:
    A prefixed hyphenated two-word string (e.g. "exp-brave-otter").
  """
  prefix = _detect_resource_type(resource_name)
  slug = _generate_slug(resource_name)
  return f"{prefix}{slug}"


def strip_prefix(nickname: str) -> str:
  """Strips the type prefix from a nickname, returning the bare slug.

  Args:
    nickname: A nickname, possibly prefixed with "exp-" or "prog-".

  Returns:
    The bare slug without prefix.
  """
  if nickname.startswith(_EXPERIMENT_PREFIX):
    return nickname[len(_EXPERIMENT_PREFIX) :]
  if nickname.startswith(_PROGRAM_PREFIX):
    return nickname[len(_PROGRAM_PREFIX) :]
  return nickname


def shorten_name(resource_name: str) -> str:
  """Extracts the short ID component from a full resource name path.

  Args:
    resource_name: The full resource path.

  Returns:
    The last path component (the resource ID).
  """
  return (
      resource_name.rsplit("/", 1)[-1]
      if "/" in resource_name
      else resource_name
  )


class NicknameIndex:
  """Bidirectional mapping between nicknames and resource names.

  Built lazily from API list responses. Handles collisions by
  appending -2, -3, etc.
  """

  def __init__(self, load_cache: bool = True) -> None:
    self._name_to_nick: dict[str, str] = {}
    self._nick_to_name: dict[str, str] = {}
    self._short_to_name: dict[str, str] = {}

    if load_cache:
      data = config.get_cache("nicknames_index", ttl_seconds=2**30)
      if data:
        self._name_to_nick = data.get("name_to_nick", {})
        self._nick_to_name = data.get("nick_to_name", {})
        self._short_to_name = data.get("short_to_name", {})

  def add(self, resource_name: str) -> str:
    """Adds a resource name and returns its prefixed nickname.

    The nickname is prefixed with ``exp-`` for experiments and ``prog-``
    for programs, based on the resource name contents.

    Args:
      resource_name: The full API resource path.

    Returns:
      A prefixed two-word nickname (e.g. "exp-brave-otter").
    """
    if resource_name in self._name_to_nick:
      return self._name_to_nick[resource_name]

    prefix = _detect_resource_type(resource_name)

    digest = hashlib.sha256(resource_name.encode()).digest()
    seed = int.from_bytes(digest[:8], "big")
    rng = random.Random(seed)
    coolname.replace_random(rng)

    slug = coolname.generate_slug(2)
    nick = f"{prefix}{slug}"
    while nick in self._nick_to_name:
      # Collision found! Generate next slug in sequence.
      slug = coolname.generate_slug(2)
      nick = f"{prefix}{slug}"

    # Restore default randomness.
    coolname.replace_random(random.Random())

    self._name_to_nick[resource_name] = nick
    self._nick_to_name[nick] = resource_name
    self._short_to_name[shorten_name(resource_name)] = resource_name
    return nick

  def to_dict(self) -> dict[str, typing.Any]:
    """Serializes the index state into a dictionary layout frame suitable.

    Returns:
      A dictionary representation of full backends collections accurately.
    """
    return {
        "name_to_nick": self._name_to_nick,
        "nick_to_name": self._nick_to_name,
        "short_to_name": self._short_to_name,
    }

  @classmethod
  def from_dict(cls, data: dict[str, typing.Any]) -> NicknameIndex:
    """Deserializes an index from stored dictionary state.

    Args:
      data: A dictionary containing serialized index mapping values.

    Returns:
      A rehydrated NicknameIndex instance commits resolving state.
    """
    idx = cls()
    idx._name_to_nick = data.get("name_to_nick", {})
    idx._nick_to_name = data.get("nick_to_name", {})
    idx._short_to_name = data.get("short_to_name", {})
    return idx

  @classmethod
  @contextlib.contextmanager
  def lock(
      cls,
  ) -> typing.Iterator[None]:
    """Provides a context manager for exclusive locking on the index file.

    Yields:
      None while lock satisfies safety concurrent access exclusions inside.
    """
    del cls  # Unused.

    lock_path = config.CACHE_DIR / "nicknames_index.lock"
    with filelock.FileLock(str(lock_path)):
      yield

  def save(self) -> None:
    """Saves the index details into persistent disk cache pass throughs."""
    config.save_cache("nicknames_index", self.to_dict())

  @classmethod
  def load(cls) -> NicknameIndex:
    """Loads index details reversing layout from persistent disk cache.

    Returns:
      A loaded NicknameIndex populated from cache else empty initial.
    """
    data = config.get_cache("nicknames_index", ttl_seconds=2**30)
    return cls.from_dict(data) if data else cls()

  @classmethod
  def get_nickname_synchronized(
      cls,
      resource_name: str,
  ) -> tuple[str, NicknameIndex]:
    """Retrieves or creates a nickname, synchronized across processes.

    Args:
      resource_name: The full absolute identifier.

    Returns:
      A tuple of (nickname_string, loaded_index_object).
    """
    with cls.lock():
      idx = cls.load()
      nick = idx.get_nickname(resource_name)
      idx.save()
      return nick, idx

  def add_many(self, resources: list[dict[str, typing.Any]]) -> None:
    """Adds multiple resources from typical API list response layouts.

    Args:
      resources: A list of item dictionaries containing 'name' string target.
    """
    for r in resources:
      name = r.get("name", "")
      if name:
        self.add(name)

  def resolve(self, identifier: str) -> str | None:
    """Resolves any identifier to a full resource name.

    Tries in order:
      1. Full resource name (passthrough).
      2. Exact prefixed nickname lookup (e.g. "exp-brave-otter").
      3. Unprefixed slug lookup — tries both "exp-" and "prog-" prefixes
         for backwards compatibility with old indexes and user convenience.
      4. Short ID lookup.

    Args:
      identifier: Prefixed nickname, bare slug, short ID, or full name.

    Returns:
      The full resource name, or None if not found.
    """
    if "/" in identifier and identifier in self._name_to_nick:
      return identifier
    # Exact match (prefixed or legacy unprefixed).
    if identifier in self._nick_to_name:
      return self._nick_to_name[identifier]
    # Try adding prefixes if the identifier has no prefix.
    if not identifier.startswith((_EXPERIMENT_PREFIX, _PROGRAM_PREFIX)):
      for pfx in (_EXPERIMENT_PREFIX, _PROGRAM_PREFIX):
        prefixed = f"{pfx}{identifier}"
        if prefixed in self._nick_to_name:
          return self._nick_to_name[prefixed]
    if identifier in self._short_to_name:
      return self._short_to_name[identifier]
    if "/" in identifier:
      return identifier
    return None

  def get_nickname(self, resource_name: str) -> str:
    """Retrieves or creates the prefixed nickname for a resource name.

    Args:
      resource_name: The full API resource path.

    Returns:
      A prefixed two-word nickname (e.g. "prog-swift-panda").
    """
    if resource_name not in self._name_to_nick:
      self.add(resource_name)
    return self._name_to_nick[resource_name]

  def nicknames(self) -> list[str]:
    """Returns all currently known nicknames.

    Returns:
      A list of prefixed nickname strings.
    """
    return list(self._nick_to_name.keys())
