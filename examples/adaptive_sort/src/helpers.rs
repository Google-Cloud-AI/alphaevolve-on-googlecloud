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

use std::cmp::Ordering;

// EVOLVE-BLOCK-START
pub fn quicksort<T: Ord + Clone>(arr: &mut [T], low: usize, high: usize) {
    if low < high {
        let pivot_index = partition(arr, low, high);
        
        // Recursively sort elements before and after partition
        if pivot_index > 0 {
            quicksort(arr, low, pivot_index - 1);
        }
        quicksort(arr, pivot_index + 1, high);
    }
}

pub fn partition<T: Ord + Clone>(arr: &mut [T], low: usize, high: usize) -> usize {
    // Choose the last element as pivot (can be evolved to use better strategies)
    let pivot = arr[high].clone();
    let mut i = low;
    
    for j in low..high {
        if arr[j] <= pivot {
            arr.swap(i, j);
            i += 1;
        }
    }
    
    arr.swap(i, high);
    i
}

// Helper function to detect if array is nearly sorted
pub fn is_nearly_sorted<T: Ord>(arr: &[T], threshold: f64) -> bool {
    if arr.len() <= 1 {
        return true;
    }
    
    let mut inversions = 0;
    let max_inversions = ((arr.len() * (arr.len() - 1)) / 2) as f64 * threshold;
    
    for i in 0..arr.len() - 1 {
        for j in i + 1..arr.len() {
            if arr[i] > arr[j] {
                inversions += 1;
                if inversions as f64 > max_inversions {
                    return false;
                }
            }
        }
    }
    
    true
}

// Helper function for insertion sort (useful for small arrays)
pub fn insertion_sort<T: Ord>(arr: &mut [T]) {
    for i in 1..arr.len() {
        let mut j = i;
        while j > 0 && arr[j - 1] > arr[j] {
            arr.swap(j, j - 1);
            j -= 1;
        }
    }
}
// EVOLVE-BLOCK-END
