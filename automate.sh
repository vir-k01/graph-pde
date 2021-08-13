#!/bin/sh

var=0     #this is for seed
i=1000      #this is for timestep
while [ $var -le 1020 ]
do
#    newvar=$((var-786))
#	sed -i "s/^SEED.*/SEED ${newvar}/" InputParams
	GSL_RNG_SEED=${var} ./ternary
	i=1000
	while [ $i -le 1500 ]
	do
		./bin2asc <<< $i > "${var}t${i}.out"
		i=$((i + 500))
	done
#	i=1100
#        ./bin2asc <<< $i > "${var}t${i}.out"
	mv *.out ascii
	for file in comp*; do mv "$file" "$var$file"; done;
	mv *comp* binary
	var=$((var + 1))
done

