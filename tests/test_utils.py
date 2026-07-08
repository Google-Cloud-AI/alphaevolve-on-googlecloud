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

from alpha_evolve.utils import fix_multi_files_program, unflatten_program_content


def test_unflatten_program_content():
    content = """File: main.py
Language: python
---
import os
print("Hello")
---
File: utils.py
---
def foo():
    pass
---"""
    files = unflatten_program_content(content)
    assert len(files) == 2
    assert files[0]["path"] == "main.py"
    assert files[0]["content"].strip() == 'import os\nprint("Hello")'
    assert files[1]["path"] == "utils.py"


def test_fix_multi_files_program():
    program = {
        "content": {"files": [{"content": 'File: main.py\n---\nprint("Hi")\n---'}]}
    }
    fix_multi_files_program(program)
    assert len(program["content"]["files"]) == 1
    assert program["content"]["files"][0]["path"] == "main.py"


def test_fix_multi_files_program_missing_content():
    program = {}
    fix_multi_files_program(program)
    assert program == {}

    program = {"content": {}}
    fix_multi_files_program(program)
    assert program == {"content": {}}


def test_fix_multi_files_program_empty_files():
    program = {"content": {"files": []}}
    fix_multi_files_program(program)
    assert program == {"content": {"files": []}}

