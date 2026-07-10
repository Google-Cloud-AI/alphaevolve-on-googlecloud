// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <mpi.h>
#include <iostream>
#include <vector>
#include <cmath>
#include <chrono>
#include <random>
#include <immintrin.h>
#include <x86intrin.h>

struct Particle {
    double x, y, z;    // Positions
    double vx, vy, vz; // Velocities
    double fx, fy, fz; // Forces
    double mass;
};

const double G = 6.67430e-11;
const double DT = 0.01;

void compute_forces_mpi(std::vector<Particle>& particles, int rank, int num_ranks) {
    int n = particles.size();
    int chunk_size = n / num_ranks;
    int start_idx = rank * chunk_size;
    int end_idx = (rank == num_ranks - 1) ? n : start_idx + chunk_size;

    // Thread-local forces array for this rank
    std::vector<double> local_fx(n, 0.0), local_fy(n, 0.0), local_fz(n, 0.0);

    // Each rank calculates forces ONLY for its assigned particle chunk
// ////////////////////////////////////////////////////////////////////////////
// EVOLVE-BLOCK-START
// ////////////////////////////////////////////////////////////////////////////
    for (int i = start_idx; i < end_idx; ++i) {
        for (int j = 0; j < n; ++j) {
            if (i == j) continue;
            double dx = particles[j].x - particles[i].x;
            double dy = particles[j].y - particles[i].y;
            double dz = particles[j].z - particles[i].z;
            double distSqr = dx*dx + dy*dy + dz*dz + 1e-9; // softening factor
            double dist = std::sqrt(distSqr);
            double force = (G * particles[i].mass * particles[j].mass) / distSqr;
            
            local_fx[i] += force * (dx / dist);
            local_fy[i] += force * (dy / dist);
            local_fz[i] += force * (dz / dist);
        }
    }
// ////////////////////////////////////////////////////////////////////////////
// EVOLVE-BLOCK-END
// ////////////////////////////////////////////////////////////////////////////

    // Synchronize forces across all MPI ranks
    MPI_Allreduce(MPI_IN_PLACE, local_fx.data(), n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, local_fy.data(), n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, local_fz.data(), n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);

    // Write back to particles
    for (int i = 0; i < n; ++i) {
        particles[i].fx = local_fx[i];
        particles[i].fy = local_fy[i];
        particles[i].fz = local_fz[i];
    }
}

double compute_total_energy(const std::vector<Particle>& particles) {
    double kinetic = 0;
    double potential = 0;
    int n = particles.size();
    for (int i = 0; i < n; ++i) {
        double v2 = particles[i].vx*particles[i].vx + particles[i].vy*particles[i].vy + particles[i].vz*particles[i].vz;
        kinetic += 0.5 * particles[i].mass * v2;
        for (int j = i + 1; j < n; ++j) {
            double dx = particles[j].x - particles[i].x;
            double dy = particles[j].y - particles[i].y;
            double dz = particles[j].z - particles[i].z;
            double dist = std::sqrt(dx*dx + dy*dy + dz*dz + 1e-9);
            potential -= (G * particles[i].mass * particles[j].mass) / dist;
        }
    }
    return kinetic + potential;
}

int main(int argc, char* argv[]) {
    MPI_Init(&argc, &argv);
    
    int rank, num_ranks;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &num_ranks);

    char processor_name[MPI_MAX_PROCESSOR_NAME];
    int name_len;
    MPI_Get_processor_name(processor_name, &name_len);
    std::cout << "[MPI Rank " << rank << " / " << num_ranks << "] Initialized on host: " << processor_name << std::endl;

    int num_particles = (argc > 1) ? std::stoi(argv[1]) : 1000;
    int steps = 100;
    
    std::vector<Particle> particles(num_particles);
    
    // Distribute particles on a uniform grid to avoid close-proximity singularities
    int grid_dim = std::ceil(std::cbrt(num_particles));
    double spacing = 10.0;
    int idx = 0;
    for (int x = 0; x < grid_dim && idx < num_particles; ++x) {
        for (int y = 0; y < grid_dim && idx < num_particles; ++y) {
            for (int z = 0; z < grid_dim && idx < num_particles; ++z) {
                particles[idx].x = x * spacing;
                particles[idx].y = y * spacing;
                particles[idx].z = z * spacing;
                particles[idx].vx = 0.0;
                particles[idx].vy = 0.0;
                particles[idx].vz = 0.0;
                particles[idx].mass = 1e9;
                idx++;
            }
        }
    }

    double initial_energy = compute_total_energy(particles);
    
    // Synchronize all ranks before starting the timer
    MPI_Barrier(MPI_COMM_WORLD);
    auto start = std::chrono::high_resolution_clock::now();
    
    for (int step = 0; step < steps; ++step) {
        compute_forces_mpi(particles, rank, num_ranks);
        for (auto& p : particles) {
            p.vx += (p.fx / p.mass) * DT;
            p.vy += (p.fy / p.mass) * DT;
            p.vz += (p.fz / p.mass) * DT;
            p.x += p.vx * DT;
            p.y += p.vy * DT;
            p.z += p.vz * DT;
        }
    }
    
    // Synchronize all ranks before stopping the timer
    MPI_Barrier(MPI_COMM_WORLD);
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed = end - start;
    
    double final_energy = compute_total_energy(particles);
    double energy_drift = std::abs((final_energy - initial_energy) / initial_energy);
    
    if (rank == 0) {
        std::cout << "TIME_MS: " << elapsed.count() << std::endl;
        std::cout << "ENERGY_DRIFT: " << energy_drift << std::endl;
    }
    
    MPI_Finalize();
    return 0;
}
