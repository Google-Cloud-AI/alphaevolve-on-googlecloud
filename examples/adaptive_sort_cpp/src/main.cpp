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
#ifndef MAIN_CPP
#define MAIN_CPP

#include <iostream>
#include <vector>
#include <string>
#include <iomanip>
#include "benchmark.hpp"
#include <random>

int main() {
    // Generate some random test data
    std::vector<std::vector<int>> test_data;
    std::mt19937 rng(42);
    std::uniform_int_distribution<int> dist(0, 1000);
    
    for (int i = 0; i < 5; ++i) {
        std::vector<int> arr;
        for (int j = 0; j < 100; ++j) {
            arr.push_back(dist(rng));
        }
        test_data.push_back(arr);
    }
    
    adaptive_sort::BenchmarkResults results = adaptive_sort::Benchmark::run_benchmark(test_data);
    
    // Print JSON output
    std::cout << "{\"times\": [";
    for (size_t i = 0; i < results.times.size(); ++i) {
        std::cout << results.times[i];
        if (i < results.times.size() - 1) std::cout << ", ";
    }
    std::cout << "], \"correctness\": [";
    for (size_t i = 0; i < results.correctness.size(); ++i) {
        std::cout << (results.correctness[i] ? "true" : "false");
        if (i < results.correctness.size() - 1) std::cout << ", ";
    }
    std::cout << "], \"adaptability_score\": " << results.adaptability_score;
    
    double mean_time = 0;
    if (!results.times.empty()) {
        double sum = 0;
        for (double t : results.times) sum += t;
        mean_time = sum / results.times.size();
    }
    double performance_score = (mean_time > 0) ? (1.0 / mean_time) : 0.0;
    
    std::cout << ", \"performance_score\": " << performance_score;
    std::cout << ", \"avg_time\": " << mean_time;
    std::cout << ", \"all_correct\": " << (std::all_of(results.correctness.begin(), results.correctness.end(), [](bool b){ return b; }) ? "true" : "false");
    std::cout << "}" << std::endl;
    
    return 0;
}

#endif // MAIN_CPP
