#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
command -v jj2lsj >/dev/null 2>&1 || jj2lsj() { jj2lsj_2025 "$@"; }
cd .

export MPI_TMP="$PWD"/tmp_mpi
mkdir -p "$MPI_TMP"
# hwloc's GL plugin makes mpirun hang under WSLg
export HWLOC_COMPONENTS="${HWLOC_COMPONENTS:--gl}"

# 1. rcsfgenerate -> odd2.c
rcsfgenerate <<'EOF'
*
0
1s(2,i)2s(2,i)2p(1,i)
1s(2,i)2p(3,i)

2s,2p
1,3
0
n
EOF
cp rcsf.out odd2.c

# 2. rcsfgenerate -> odd.c
rcsfgenerate <<'EOF'
*
0
1s(2,*)2s(2,*)2p(1,*)
1s(2,*)2p(3,*)

6s,6p,6d,6f,6g,6h
1,3
2
n
EOF
cp rcsf.out odd.c

# 3. rcsfsplit odd
rcsfsplit <<'EOF'
odd
4
3s,3p,3d
3
4s,4p,4d,4f
4
5s,5p,5d,5f,5g
5
6s,6p,6d,6f,6g,6h
6
EOF

# 4. rcsfgenerate -> even2.c
rcsfgenerate <<'EOF'
*
0
1s(2,i)2s(1,i)2p(2,i)

2s,2p
1,5
0
n
EOF
cp rcsf.out even2.c

# 5. rcsfgenerate -> even.c
rcsfgenerate <<'EOF'
*
0
1s(2,*)2s(1,*)2p(2,*)

6s,6p,6d,6f,6g,6h
1,5
2
n
EOF
cp rcsf.out even.c

# 6. rcsfsplit even
rcsfsplit <<'EOF'
even
4
3s,3p,3d
3
4s,4p,4d,4f
4
5s,5p,5d,5f,5g
5
6s,6p,6d,6f,6g,6h
6
EOF

# 7. rnucleus
rnucleus <<'EOF'
42
96
n
96
1
1
1
EOF

# 8. rangular (odd2.c)
cp odd2.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 9. rwfnestimate
rwfnestimate <<'EOF'
y
3
*
EOF

# 10. rmcdhf -> odd2
mpirun -np 4 rmcdhf_mpi > outodd_rmcdhf_initial <<'EOF'
y
1
1
5
*
*
100
EOF
rsave odd2

# 11. rangular (even2.c)
cp even2.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 12. rwfnestimate
rwfnestimate <<'EOF'
y
3
*
EOF

# 13. rmcdhf -> even2
mpirun -np 4 rmcdhf_mpi > outeven_rmcdhf_initial <<'EOF'
y
1,2,3
1,2,3
1,2
5
*
*
100
EOF
rsave even2

# 14. rangular (odd3.c)
cp odd3.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 15. rwfnestimate
rwfnestimate <<'EOF'
y
1
odd2.w
*
3
*
EOF

# 16. rmcdhf -> odd3
mpirun -np 4 rmcdhf_mpi > outodd_rmcdhf_3 <<'EOF'
y
1
1
5
3*

100
EOF
rsave odd3

# 17. jj2lsj odd3
jj2lsj <<'EOF'
odd3
n
y
y
EOF

# 18. rangular (odd4.c)
cp odd4.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 19. rwfnestimate
rwfnestimate <<'EOF'
y
1
odd3.w
*
3
*
EOF

# 20. rmcdhf -> odd4
mpirun -np 4 rmcdhf_mpi > outodd_rmcdhf_4 <<'EOF'
y
1
1
5
4*

100
EOF
rsave odd4

# 21. jj2lsj odd4
jj2lsj <<'EOF'
odd4
n
y
y
EOF

# 22. rangular (odd5.c)
cp odd5.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 23. rwfnestimate
rwfnestimate <<'EOF'
y
1
odd4.w
*
3
*
EOF

# 24. rmcdhf -> odd5
mpirun -np 4 rmcdhf_mpi > outodd_rmcdhf_5 <<'EOF'
y
1
1
5
5*

100
EOF
rsave odd5

# 25. jj2lsj odd5
jj2lsj <<'EOF'
odd5
n
y
y
EOF

# 26. rangular (odd6.c)
cp odd6.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 27. rwfnestimate
rwfnestimate <<'EOF'
y
1
odd5.w
*
3
*
EOF

# 28. rmcdhf -> odd6
mpirun -np 4 rmcdhf_mpi > outodd_rmcdhf_6 <<'EOF'
y
1
1
5
6*

100
EOF
rsave odd6

# 29. jj2lsj odd6
jj2lsj <<'EOF'
odd6
n
y
y
EOF

# 30. rci oddCI6
cp odd6.c oddCI6.c
cp odd6.w oddCI6.w
mpirun -np 4 rci_mpi > outodd_rci <<'EOF'
y
oddCI6
y
y
1.d-6
y
n
n
y
4
1
1
EOF

# 31. jj2lsj oddCI6
jj2lsj <<'EOF'
oddCI6
y
y
y
EOF

# 32. rangular (even3.c)
cp even3.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 33. rwfnestimate
rwfnestimate <<'EOF'
y
1
even2.w
*
3
*
EOF

# 34. rmcdhf -> even3
mpirun -np 4 rmcdhf_mpi > outeven_rmcdhf_3 <<'EOF'
y
1,2,3
1,2,3
1,2
5
3*

100
EOF
rsave even3

# 35. jj2lsj even3
jj2lsj <<'EOF'
even3
n
y
y
EOF

# 36. rangular (even4.c)
cp even4.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 37. rwfnestimate
rwfnestimate <<'EOF'
y
1
even3.w
*
3
*
EOF

# 38. rmcdhf -> even4
mpirun -np 4 rmcdhf_mpi > outeven_rmcdhf_4 <<'EOF'
y
1,2,3
1,2,3
1,2
5
4*

100
EOF
rsave even4

# 39. jj2lsj even4
jj2lsj <<'EOF'
even4
n
y
y
EOF

# 40. rangular (even5.c)
cp even5.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 41. rwfnestimate
rwfnestimate <<'EOF'
y
1
even4.w
*
3
*
EOF

# 42. rmcdhf -> even5
mpirun -np 4 rmcdhf_mpi > outeven_rmcdhf_5 <<'EOF'
y
1,2,3
1,2,3
1,2
5
5*

100
EOF
rsave even5

# 43. jj2lsj even5
jj2lsj <<'EOF'
even5
n
y
y
EOF

# 44. rangular (even6.c)
cp even6.c rcsf.inp
mpirun -np 4 rangular_mpi <<'EOF'
y
EOF

# 45. rwfnestimate
rwfnestimate <<'EOF'
y
1
even5.w
*
3
*
EOF

# 46. rmcdhf -> even6
mpirun -np 4 rmcdhf_mpi > outeven_rmcdhf_6 <<'EOF'
y
1,2,3
1,2,3
1,2
5
6*

100
EOF
rsave even6

# 47. jj2lsj even6
jj2lsj <<'EOF'
even6
n
y
y
EOF

# 48. rci evenCI6
cp even6.c evenCI6.c
cp even6.w evenCI6.w
mpirun -np 4 rci_mpi > outeven_rci <<'EOF'
y
evenCI6
y
y
1.d-6
y
n
n
y
4
1,2,3
1,2,3
1,2
EOF

# 49. jj2lsj evenCI6
jj2lsj <<'EOF'
evenCI6
y
y
y
EOF

# 50. rbiotransform
mpirun -np 4 rbiotransform_mpi > out_rbiotransform <<'EOF'
y
y
oddCI6
evenCI6
y
EOF

# 51. rtransition
mpirun -np 4 rtransition_mpi > out_transition <<'EOF'
y
y
oddCI6
evenCI6
E1
EOF

