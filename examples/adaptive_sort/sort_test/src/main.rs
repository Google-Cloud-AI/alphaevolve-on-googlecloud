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

use rand::prelude::*;
use sort_test::{adaptive_sort, run_benchmark};
use std::time::Instant;

fn main() {
    // Generate test datasets with different characteristics
    let test_data = vec![
        // Random data
        generate_random_data(1000),
        generate_random_data(10000),
        // Nearly sorted data
        generate_nearly_sorted_data(1000, 0.05),
        generate_nearly_sorted_data(10000, 0.05),
        // Reverse sorted data
        generate_reverse_sorted_data(1000),
        generate_reverse_sorted_data(10000),
        // Data with many duplicates
        generate_data_with_duplicates(1000, 10),
        generate_data_with_duplicates(10000, 100),
        // Partially sorted data
        generate_partially_sorted_data(1000, 0.3),
        generate_partially_sorted_data(10000, 0.3),
    ];

    let results = run_benchmark(test_data);

    // Calculate metrics
    let all_correct = results.correctness.iter().all(|&c| c);
    let correctness_score = if all_correct { 1.0 } else { 0.0 };

    let avg_time: f64 = results.times.iter().sum::<f64>() / results.times.len() as f64;

    // Performance score (normalized, assuming baseline of 0.1 seconds for largest dataset)
    let performance_score = 1.0 / (1.0 + avg_time * 10.0);

    // Output results as JSON
    println!("{{");
    println!("  \"correctness\": {},", correctness_score);
    println!("  \"avg_time\": {},", avg_time);
    println!("  \"performance_score\": {},", performance_score);
    println!("  \"adaptability_score\": {},", results.adaptability_score);
    println!("  \"times\": {:?},", results.times);
    println!("  \"all_correct\": {}", all_correct);
    println!("}}");
}

fn generate_random_data(size: usize) -> Vec<i32> {
    let mut rng = rand::rng();
    (0..size).map(|_| rng.random::<i32>() % 10000).collect()
}

fn generate_nearly_sorted_data(size: usize, disorder_rate: f64) -> Vec<i32> {
    let mut data: Vec<i32> = (0..size as i32).collect();
    let swaps = (size as f64 * disorder_rate) as usize;
    let mut rng = rand::rng();
    for _ in 0..swaps {
        let i = rng.random::<u64>() as usize % size;
        let j = rng.random::<u64>() as usize % size;
        data.swap(i, j);
    }

    data
}

fn generate_reverse_sorted_data(size: usize) -> Vec<i32> {
    (0..size as i32).rev().collect()
}

fn generate_data_with_duplicates(size: usize, unique_values: usize) -> Vec<i32> {
    let mut rng = rand::rng();
    (0..size)
        .map(|_| rng.random::<i32>() % unique_values as i32)
        .collect()
}

fn generate_partially_sorted_data(size: usize, sorted_fraction: f64) -> Vec<i32> {
    let mut rng = rand::rng();
    let sorted_size = (size as f64 * sorted_fraction) as usize;
    let mut data = Vec::with_capacity(size);

    // Add sorted portion
    data.extend((0..sorted_size as i32));

    // Add random portion
    data.extend((0..(size - sorted_size)).map(|_| rng.random::<i32>() % 10000));

    data
}
