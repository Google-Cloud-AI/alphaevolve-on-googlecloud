CXX = mpicxx
CXXFLAGS = -O3 -march=native -std=c++17

.PHONY: all clean evaluator.sh

all: nbody_sim evaluator.sh

nbody_sim: main.cpp
	$(CXX) $(CXXFLAGS) main.cpp -o nbody_sim
	cp nbody_sim /var/tmp/nbody_sim || true

clean:
	rm -f nbody_sim /var/tmp/nbody_sim evaluator.sh

evaluator.sh:
	cat evaluator.sh.template > evaluator.sh
	chmod +x evaluator.sh


