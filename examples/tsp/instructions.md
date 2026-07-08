Minimise the total tour length for the Travelling Salesman Problem
with 50 cities whose coordinates are drawn uniformly from [0,1]x[0,1].

The function construct_tour(distances, n) receives the full n x n
Euclidean distance matrix and the number of cities, and must return a
permutation of [0, n) representing the visit order. The tour returns
to the starting city.

Optimise for the shortest possible total tour length across 5 fixed
random instances.

You may use any algorithmic technique: 2-opt, or-opt, Lin-Kernighan,
simulated annealing, genetic algorithms, greedy construction
heuristics, etc.

numpy is available as np.
