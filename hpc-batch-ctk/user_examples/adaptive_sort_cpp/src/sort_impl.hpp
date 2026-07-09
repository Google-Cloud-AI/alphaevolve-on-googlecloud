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

// Implementation is included in header for templates, 
// but we can put non-template helper implementations here if we extracted them.
// For simplicity with templates, we'll keep implementation in hpp or include this at bottom of hpp.
// Actually, since we decided to include "sort.cpp" at the end of "sort.hpp", 
// we will put the implementation here.

#ifndef ADAPTIVE_SORT_IMPL_HPP
#define ADAPTIVE_SORT_IMPL_HPP

#include "sort.hpp"
#include <iostream>

namespace adaptive_sort {

// EVOLVE-BLOCK-START
template <typename T>
void quicksort(std::vector<T>& arr, int low, int high) {
    if (low < high) {
        int pivot_index = partition(arr, low, high);
        
        // Recursively sort elements before and after partition
        if (pivot_index > 0) {
            quicksort(arr, low, pivot_index - 1);
        }
        quicksort(arr, pivot_index + 1, high);
    }
}

template <typename T>
int partition(std::vector<T>& arr, int low, int high) {
    // Choose the last element as pivot (can be evolved to use better strategies)
    T pivot = arr[high];
    int i = low;
    
    for (int j = low; j < high; ++j) {
        if (arr[j] <= pivot) {
            std::swap(arr[i], arr[j]);
            i++;
        }
    }
    
    std::swap(arr[i], arr[high]);
    return i;
}

template <typename T>
bool is_nearly_sorted(const std::vector<T>& arr, double threshold) {
    if (arr.size() <= 1) {
        return true;
    }
    
    long long inversions = 0;
    double max_inversions = ((double)arr.size() * (arr.size() - 1) / 2.0) * threshold;
    
    for (size_t i = 0; i < arr.size() - 1; ++i) {
        for (size_t j = i + 1; j < arr.size(); ++j) {
            if (arr[i] > arr[j]) {
                inversions++;
                if ((double)inversions > max_inversions) {
                    return false;
                }
            }
        }
    }
    
    return true;
}

template <typename T>
void insertion_sort(std::vector<T>& arr) {
    for (size_t i = 1; i < arr.size(); ++i) {
        size_t j = i;
        while (j > 0 && arr[j - 1] > arr[j]) {
            std::swap(arr[j], arr[j - 1]);
            j--;
        }
    }
}
// EVOLVE-BLOCK-END

} // namespace adaptive_sort

#endif // ADAPTIVE_SORT_IMPL_HPP
