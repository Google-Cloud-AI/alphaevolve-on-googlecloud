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
#include "benchmark.hpp"

namespace adaptive_sort {

BenchmarkResults Benchmark::run_benchmark(const std::vector<std::vector<int>>& test_data) {
    BenchmarkResults results;
    results.adaptability_score = 0.0;

    for (const auto& data : test_data) {
        std::vector<int> arr = data; // Copy data
        
        auto start = std::chrono::high_resolution_clock::now();
        adaptive_sort(arr);
        auto end = std::chrono::high_resolution_clock::now();
        
        std::chrono::duration<double> elapsed = end - start;
        results.times.push_back(elapsed.count());
        
        // Check if correctly sorted
        bool is_sorted = true;
        for (size_t i = 0; i < arr.size() - 1; ++i) {
            if (arr[i] > arr[i + 1]) {
                is_sorted = false;
                break;
            }
        }
        results.correctness.push_back(is_sorted);
    }
    
    // Calculate adaptability score based on performance variance
    if (results.times.size() > 1) {
        double sum = std::accumulate(results.times.begin(), results.times.end(), 0.0);
        double mean_time = sum / results.times.size();
        
        double variance_sum = 0.0;
        for (double t : results.times) {
            variance_sum += std::pow(t - mean_time, 2);
        }
        double variance = variance_sum / results.times.size();
        
        // Lower variance means better adaptability
        results.adaptability_score = 1.0 / (1.0 + std::sqrt(variance));
    } else {
        results.adaptability_score = 1.0; // Default if only 1 run
    }
    
    return results;
}

} // namespace adaptive_sort
