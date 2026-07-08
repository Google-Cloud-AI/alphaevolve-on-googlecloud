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
import re
from typing import Any, Dict, List


def unflatten_program_content(flat_content: str) -> List[Dict[str, Any]]:
    """Unflattens program content from a single string to a list of files."""
    # 1. Extract Top-Level Description (appears before the first "File:")
    # We use a non-greedy match up to the first double newline or File start
    # top_desc_match = re.match(
    #     r"(?:Description: )?(?P<desc>.+?)\n\nFile:", flat_content, re.DOTALL
    # )
    # Program description extraction logic can be added here if needed.

    # 2. Extract Files
    # We use [^\n]+ for headers to ensure they stop at the end of the line.
    # We use re.DOTALL so the content capture (.*?) can span multiple lines.
    file_pattern = re.compile(
        r"""
        ^File:\s+(?P<path>[^\n]+)\n                 # Path: match non-newlines
        (?:Language:\s+(?P<language>[^\n]+)\n)?     # Language: match non-newlines
        (?:Description:\s+(?P<description>[^\n]+)\n)? # Desc: match non-newlines
        ---\n                                       # Start Separator
        (?P<content>.*?)
        \n---""",  # End Separator
        re.MULTILINE | re.VERBOSE | re.DOTALL,
    )

    files_data = []

    for match in file_pattern.finditer(flat_content):
        files_data.append(
            {"path": match.group("path").strip(), "content": match.group("content")}
        )

    return files_data


def fix_multi_files_program(program: Dict[str, Any]) -> None:
    """Fixes the program content if it's flattened into a single file."""
    if "content" not in program or "files" not in program["content"]:
        return

    if not program["content"]["files"]:
        return

    first_file_content = program["content"]["files"][0]["content"]
    if first_file_content.startswith("File:"):
        files = unflatten_program_content(first_file_content)
        # print("First file:", first_file_content)
        # print("FILES:", files)
        program["content"]["files"] = files
