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
#ifndef BENCHMARK_HPP
#define BENCHMARK_HPP

#include <vector>
#include <chrono>
#include <cmath>
#include <numeric>
#include "sort.hpp"

namespace adaptive_sort {

struct BenchmarkResults {
    std::vector<double> times;
    std::vector<bool> correctness;
    double adaptability_score;
};

class Benchmark {
public:
    static BenchmarkResults run_benchmark(const std::vector<std::vector<int>>& test_data);
};

} // namespace adaptive_sort

#endif // BENCHMARK_HPP
