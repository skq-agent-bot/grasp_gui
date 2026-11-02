#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
cd .

export MPI_TMP="$PWD"/tmp_mpi
mkdir -p "$MPI_TMP"
# hwloc's GL plugin makes mpirun hang under WSLg
export HWLOC_COMPONENTS="${HWLOC_COMPONENTS:--gl}"

# 1. rcsfggenerate_csfg -> odd2.g
rcsfggenerate_csfg <<'EOF'
0
1s(2,i)2s(2,i)2p(1,i)
1s(2,i)2p(3,i)

2s,2p
1,3
0
n
EOF
cp rcsfg.out odd2.g
cp rlabel.out odd2.l

# 2. rcsfggenerate_csfg -> odd.g
rcsfggenerate_csfg <<'EOF'
0
1s(2,*)2s(2,*)2p(1,*)
1s(2,*)2p(3,*)

2s,2p
1,3
0
y
1s(2,*)2s(2,*)2p(1,*)
1s(2,*)2p(3,*)

6s,6p,6d,6f,6g,6h
1,3
2
n
EOF
cp rcsfg.out odd.g
cp rlabel.out odd.l

# 3. rcsfgsplit_csfg odd
cp odd.l rlabel.inp
rcsfgsplit_csfg <<'EOF'
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

# 4. rcsfggenerate_csfg -> even2.g
rcsfggenerate_csfg <<'EOF'
0
1s(2,i)2s(1,i)2p(2,i)

2s,2p
1,5
0
n
EOF
cp rcsfg.out even2.g
cp rlabel.out even2.l

# 5. rcsfggenerate_csfg -> even.g
rcsfggenerate_csfg <<'EOF'
0
1s(2,*)2s(1,*)2p(2,*)

2s,2p
1,5
0
y
1s(2,*)2s(1,*)2p(2,*)

6s,6p,6d,6f,6g,6h
1,5
2
n
EOF
cp rcsfg.out even.g
cp rlabel.out even.l

# 6. rcsfgsplit_csfg even
cp even.l rlabel.inp
rcsfgsplit_csfg <<'EOF'
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

# 8. rangular_csfg (odd2)
cp odd2.g rcsfg.inp
cp odd2.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 9. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
3
*
EOF

# 10. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd2 <<'EOF'
y
1
1
5
*
*
100
EOF

# 11. cp
cp rwfn.out rwfn.inp < /dev/null

# 12. rmcdhf_csfg -> odd2
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd2 <<'EOF'
y
1
1
5
*
*
100
EOF
rsave_csfg odd2

# 13. jj2lsj_csfg odd2
jj2lsj_csfg <<'EOF'
odd2
n
y
y
EOF

# 14. rangular_csfg (even2)
cp even2.g rcsfg.inp
cp even2.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 15. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
3
*
EOF

# 16. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even2 <<'EOF'
y
1,2,3
1,2,3
1,2
5
*
*
100
EOF

# 17. cp
cp rwfn.out rwfn.inp < /dev/null

# 18. rmcdhf_csfg -> even2
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even2 <<'EOF'
y
1,2,3
1,2,3
1,2
5
*
*
100
EOF
rsave_csfg even2

# 19. jj2lsj_csfg even2
jj2lsj_csfg <<'EOF'
even2
n
y
y
EOF

# 20. rlevels_csfg
rlevels_csfg odd2.m even2.m > n2.lev < /dev/null

# 21. rangular_csfg (odd3)
cp odd3.g rcsfg.inp
cp odd3.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 22. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
odd2.w
*
3
*
EOF

# 23. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd3 <<'EOF'
y
1
1
5
3*

100
EOF

# 24. cp
cp rwfn.out rwfn.inp < /dev/null

# 25. rmcdhf_csfg -> odd3
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd3 <<'EOF'
y
1
1
5
3*

100
EOF
rsave_csfg odd3

# 26. jj2lsj_csfg odd3
jj2lsj_csfg <<'EOF'
odd3
n
y
y
EOF

# 27. rangular_csfg (odd4)
cp odd4.g rcsfg.inp
cp odd4.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 28. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
odd3.w
*
3
*
EOF

# 29. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd4 <<'EOF'
y
1
1
5
4*

100
EOF

# 30. cp
cp rwfn.out rwfn.inp < /dev/null

# 31. rmcdhf_csfg -> odd4
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd4 <<'EOF'
y
1
1
5
4*

100
EOF
rsave_csfg odd4

# 32. jj2lsj_csfg odd4
jj2lsj_csfg <<'EOF'
odd4
n
y
y
EOF

# 33. rangular_csfg (odd5)
cp odd5.g rcsfg.inp
cp odd5.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 34. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
odd4.w
*
3
*
EOF

# 35. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd5 <<'EOF'
y
1
1
5
5*

100
EOF

# 36. cp
cp rwfn.out rwfn.inp < /dev/null

# 37. rmcdhf_csfg -> odd5
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd5 <<'EOF'
y
1
1
5
5*

100
EOF
rsave_csfg odd5

# 38. jj2lsj_csfg odd5
jj2lsj_csfg <<'EOF'
odd5
n
y
y
EOF

# 39. rangular_csfg (odd6)
cp odd6.g rcsfg.inp
cp odd6.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 40. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
odd5.w
*
3
*
EOF

# 41. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd6 <<'EOF'
y
1
1
5
6*

100
EOF

# 42. cp
cp rwfn.out rwfn.inp < /dev/null

# 43. rmcdhf_csfg -> odd6
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_odd6 <<'EOF'
y
1
1
5
6*

100
EOF
rsave_csfg odd6

# 44. jj2lsj_csfg odd6
jj2lsj_csfg <<'EOF'
odd6
n
y
y
EOF

# 45. rci_csfg oddCI6
cp odd6.g oddCI6.g
cp odd6.l oddCI6.l
cp odd6.w oddCI6.w
mpirun -np 4 rci_csfg_mpi > out_rci_odd <<'EOF'
y
oddCI6
y
y
1.0d-6
n
15
n
14
y
n
n
y
2
8
1
1
EOF

# 46. jj2lsj_csfg oddCI6
jj2lsj_csfg <<'EOF'
oddCI6
y
y
y
EOF

# 47. rangular_csfg (even3)
cp even3.g rcsfg.inp
cp even3.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 48. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
even2.w
*
3
*
EOF

# 49. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even3 <<'EOF'
y
1,2,3
1,2,3
1,2
5
3*

100
EOF

# 50. cp
cp rwfn.out rwfn.inp < /dev/null

# 51. rmcdhf_csfg -> even3
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even3 <<'EOF'
y
1,2,3
1,2,3
1,2
5
3*

100
EOF
rsave_csfg even3

# 52. jj2lsj_csfg even3
jj2lsj_csfg <<'EOF'
even3
n
y
y
EOF

# 53. rangular_csfg (even4)
cp even4.g rcsfg.inp
cp even4.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 54. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
even3.w
*
3
*
EOF

# 55. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even4 <<'EOF'
y
1,2,3
1,2,3
1,2
5
4*

100
EOF

# 56. cp
cp rwfn.out rwfn.inp < /dev/null

# 57. rmcdhf_csfg -> even4
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even4 <<'EOF'
y
1,2,3
1,2,3
1,2
5
4*

100
EOF
rsave_csfg even4

# 58. jj2lsj_csfg even4
jj2lsj_csfg <<'EOF'
even4
n
y
y
EOF

# 59. rangular_csfg (even5)
cp even5.g rcsfg.inp
cp even5.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 60. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
even4.w
*
3
*
EOF

# 61. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even5 <<'EOF'
y
1,2,3
1,2,3
1,2
5
5*

100
EOF

# 62. cp
cp rwfn.out rwfn.inp < /dev/null

# 63. rmcdhf_csfg -> even5
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even5 <<'EOF'
y
1,2,3
1,2,3
1,2
5
5*

100
EOF
rsave_csfg even5

# 64. jj2lsj_csfg even5
jj2lsj_csfg <<'EOF'
even5
n
y
y
EOF

# 65. rangular_csfg (even6)
cp even6.g rcsfg.inp
cp even6.l rlabel.inp
mpirun -np 4 rangular_csfg_mpi <<'EOF'
y
EOF

# 66. rwfnestimate_csfg
rwfnestimate_csfg <<'EOF'
y
1
even5.w
*
3
*
EOF

# 67. rmcdhf_csfg
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even6 <<'EOF'
y
1,2,3
1,2,3
1,2
5
6*

100
EOF

# 68. cp
cp rwfn.out rwfn.inp < /dev/null

# 69. rmcdhf_csfg -> even6
mpirun -np 4 rmcdhf_csfg_mpi > out_rmcdhf_even6 <<'EOF'
y
1,2,3
1,2,3
1,2
5
6*

100
EOF
rsave_csfg even6

# 70. jj2lsj_csfg even6
jj2lsj_csfg <<'EOF'
even6
n
y
y
EOF

# 71. rci_csfg evenCI6
cp even6.g evenCI6.g
cp even6.l evenCI6.l
cp even6.w evenCI6.w
mpirun -np 4 rci_csfg_mpi > out_rci_even <<'EOF'
y
evenCI6
y
y
1.0d-6
n
15
n
14
y
n
n
y
2
2
1,2,3
1,2,3
1,2
EOF

# 72. jj2lsj_csfg evenCI6
jj2lsj_csfg <<'EOF'
evenCI6
y
y
y
EOF

# 73. rlevels_csfg
rlevels_csfg odd3.m even3.m > n3.lev < /dev/null

# 74. rlevels_csfg
rlevels_csfg odd4.m even4.m > n4.lev < /dev/null

# 75. rlevels_csfg
rlevels_csfg odd5.m even5.m > n5.lev < /dev/null

# 76. rlevels_csfg
rlevels_csfg odd6.m even6.m > n6.lev < /dev/null

# 77. rlevels_csfg
rlevels_csfg oddCI6.cm evenCI6.cm > n6CI.clev < /dev/null

# 78. rbiotransform
mpirun -np 4 rbiotransform_mpi > out_rbiotransform <<'EOF'
y
y
oddCI6
evenCI6
y
EOF

# 79. rtransition
mpirun -np 4 rtransition_mpi > out_transition <<'EOF'
y
y
oddCI6
evenCI6
E1
EOF

