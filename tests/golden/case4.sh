#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
cd .

# 1. rcsfgenerate -> DF.c
rcsfgenerate <<'EOF'
*
0
1s(2,i)2s(1,i)

2s
1,1
0
y
1s(2,i)2p(1,i)

1s,2p
1,3
0
n
EOF
cp rcsf.out DF.c

# 2. rcsfgenerate -> even.c
rcsfgenerate <<'EOF'
*
0
1s(2,*)2s(1,*)

4s,4p,4d,4f
1,1
3
n
EOF
cp rcsf.out even.c

# 3. rcsfsplit even
rcsfsplit <<'EOF'
even
2
3s,3p,3d
3
4s,4p,4d,4f
4
EOF

# 4. rcsfgenerate -> odd.c
rcsfgenerate <<'EOF'
*
0
1s(2,*)2p(1,*)

4s,4p,4d,4f
1,3
3
n
EOF
cp rcsf.out odd.c

# 5. rcsfsplit odd
rcsfsplit <<'EOF'
odd
2
3s,3p,3d
3
4s,4p,4d,4f
4
EOF

# 6. rnucleus
rnucleus <<'EOF'
60
150
n
150
1
1
1
EOF

# 7. rangular (DF.c)
cp DF.c rcsf.inp
rangular <<'EOF'
y
EOF

# 8. rwfnestimate
rwfnestimate <<'EOF'
y
3
*
EOF

# 9. rmcdhf -> DF
rmcdhf > out_rmcdhf_DF <<'EOF'
y
1
1
1
5
*
*
100
EOF
rsave DF

# 10. cp
cp DF.w even2.w < /dev/null

# 11. cp
cp DF.w odd2.w < /dev/null

# 12. rangular (even3.c)
cp even3.c rcsf.inp
rangular <<'EOF'
y
EOF

# 13. rwfnestimate
rwfnestimate <<'EOF'
y
1
even2.w
*
3
*
EOF

# 14. rmcdhf -> even3
rmcdhf > outeven_rmcdhf_3 <<'EOF'
y
1
3*

100
EOF
rsave even3

# 15. rangular (even4.c)
cp even4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 16. rwfnestimate
rwfnestimate <<'EOF'
y
1
even3.w
*
3
*
EOF

# 17. rmcdhf -> even4
rmcdhf > outeven_rmcdhf_4 <<'EOF'
y
1
4*

100
EOF
rsave even4

# 18. rci evenCI4
cp even4.c evenCI4.c
cp even4.w evenCI4.w
rci > outeven_rci <<'EOF'
y
evenCI4
y
y
1.d-6
y
n
n
y
4
1
EOF

# 19. ris4 evenCI4
ris4 > outeven_ris4 <<'EOF'
y
evenCI4
y
y
n
EOF

# 20. rangular (odd3.c)
cp odd3.c rcsf.inp
rangular <<'EOF'
y
EOF

# 21. rwfnestimate
rwfnestimate <<'EOF'
y
1
odd2.w
*
3
*
EOF

# 22. rmcdhf -> odd3
rmcdhf > outodd_rmcdhf_3 <<'EOF'
y
1
1
5
3*

100
EOF
rsave odd3

# 23. rangular (odd4.c)
cp odd4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 24. rwfnestimate
rwfnestimate <<'EOF'
y
1
odd3.w
*
3
*
EOF

# 25. rmcdhf -> odd4
rmcdhf > outodd_rmcdhf_4 <<'EOF'
y
1
1
5
4*

100
EOF
rsave odd4

# 26. rci oddCI4
cp odd4.c oddCI4.c
cp odd4.w oddCI4.w
rci > outodd_rci <<'EOF'
y
oddCI4
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

# 27. ris4 oddCI4
ris4 > outodd_ris4 <<'EOF'
y
oddCI4
y
y
n
EOF

# 28. fical
fical > out_fical_spherical <<'EOF'
n
evenCI4
oddCI4
y
y
both
meV
y
y
141.907719d0,4.9123d0,2.3d0,0.d0,0.d0,0.d0
149.920887d0,5.0400d0,2.3d0,0.d0,0.d0,0.d0
EOF

# 29. cp
cp evenCI4.oddCI4.cfi spherical_150Nd.fci < /dev/null

# 30. fical
fical > out_fical_deformed <<'EOF'
n
evenCI4
oddCI4
y
y
both
meV
y
y
141.907719d0,4.9123d0,2.3d0,0.d0,0.d0,0.d0
149.920887d0,5.0400d0,2.3d0,0.d0,0.28d0,0.d0
EOF

# 31. cp
cp evenCI4.oddCI4.cfi deformed_150Nd.fci < /dev/null

