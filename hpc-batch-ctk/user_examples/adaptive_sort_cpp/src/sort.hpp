// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#ifndef ADAPTIVE_SORT_HPP
#define ADAPTIVE_SORT_HPP

#include <vector>
#include <algorithm>

namespace adaptive_sort {


template <typename T>
void quicksort(std::vector<T>& arr, int low, int high);

template <typename T>
int partition(std::vector<T>& arr, int low, int high);

template <typename T>
bool is_nearly_sorted(const std::vector<T>& arr, double threshold);

template <typename T>
void insertion_sort(std::vector<T>& arr);


// Main adaptive sort function
// EVOLVE-BLOCK-START
// Initial implementation: Simple quicksort
// This can be evolved to:
// - Hybrid algorithms (introsort, timsort-like)
// - Adaptive pivot selection
// - Special handling for nearly sorted data
// - Switching to different algorithms based on data characteristics
template <typename T>
void adaptive_sort(std::vector<T>& arr) {
    if (arr.size() <= 1) {
        return;
    }
    
    // Use quicksort as the base implementation
    quicksort(arr, 0, arr.size() - 1);
}
// EVOLVE-BLOCK-END

} // namespace adaptive_sort

#include "sort_impl.hpp" // Include implementation for templates if needed, or keep definitions in hpp

#endif // ADAPTIVE_SORT_HPP
