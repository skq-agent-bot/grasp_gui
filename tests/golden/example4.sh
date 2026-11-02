#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
cd .

# 1. rnucleus
rnucleus <<'EOF'
26
56
n
55.845
1
1
1
EOF

# 2. rcsfgenerate -> evenmr.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(2,i)
2s(2,i)2p(6,i)3p(2,i)
2s(2,i)2p(6,i)3s(1,i)3d(1,i)

3s,3p,3d
0,6
0
n
EOF
cp rcsf.out evenmr.c

# 3. rangular (evenmr.c)
cp evenmr.c rcsf.inp
rangular <<'EOF'
y
EOF

# 4. rwfnestimate
rwfnestimate <<'EOF'
y
2
*
EOF

# 5. rmcdhf -> evenmr
rmcdhf <<'EOF'
y
1-3
1-2
1-4
1
5
*
*
100
EOF
rsave evenmr

# 6. rcsfgenerate -> even4.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,5)3s(2,*)
2s(2,1)2p(6,i)3s(2,*)
2s(2,i)2p(6,5)3p(2,*)
2s(2,1)2p(6,i)3p(2,*)
2s(2,i)2p(6,5)3s(1,*)3d(1,*)
2s(2,1)2p(6,i)3s(1,*)3d(1,*)

4s,4p,4d,4f
0,6
2
n
EOF
cp rcsf.out even4.c

# 7. rangular (even4.c)
cp even4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 8. rwfnestimate
rwfnestimate <<'EOF'
y
1
evenmr.w
*
2
*
EOF

# 9. rmcdhf -> even4
rmcdhf <<'EOF'
y
1-3
1-2
1-4
1
5
4*

100
EOF
rsave even4

# 10. rci even4
rci <<'EOF'
y
even4
y
y
1.d-6
y
n
n
y
4
1-3
1-2
1-4
1
EOF

# 11. jj2lsj even4
jj2lsj <<'EOF'
even4
y
y
y
EOF

# 12. rcsfgenerate -> oddmr.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(1,i)3p(1,i)
2s(2,i)2p(6,i)3p(1,i)3d(1,i)

3s,3p,3d
0,8
0
n
EOF
cp rcsf.out oddmr.c

# 13. rangular (oddmr.c)
cp oddmr.c rcsf.inp
rangular <<'EOF'
y
EOF

# 14. rwfnestimate
rwfnestimate <<'EOF'
y
2
*
EOF

# 15. rmcdhf -> oddmr
rmcdhf <<'EOF'
y
1-2
1-5
1-5
1-3
1
5
*
*
100
EOF
rsave oddmr

# 16. rcsfgenerate -> odd4.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,5)3s(1,*)3p(1,*)
2s(2,1)2p(6,i)3s(1,*)3p(1,*)
2s(2,i)2p(6,5)3p(1,*)3d(1,*)
2s(2,1)2p(6,i)3p(1,*)3d(1,*)

4s,4p,4d,4f
0,8
2
n
EOF
cp rcsf.out odd4.c

# 17. rangular (odd4.c)
cp odd4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 18. rwfnestimate
rwfnestimate <<'EOF'
y
1
oddmr.w
*
2
*
EOF

# 19. rmcdhf -> odd4
rmcdhf <<'EOF'
y
1-2
1-5
1-5
1-3
1
5
4*

100
EOF
rsave odd4

# 20. rci odd4
rci <<'EOF'
y
odd4
y
y
1.d-6
y
n
n
y
4
1-2
1-5
1-5
1-3
1
EOF

# 21. jj2lsj odd4
jj2lsj <<'EOF'
odd4
y
y
y
EOF

# 22. rlevels
rlevels even4.cm odd4.cm > energy4 < /dev/null

# 23. rlevelseV
rlevelseV even4.cm odd4.cm > energy4eV < /dev/null

# 24. rbiotransform
rbiotransform > out_rbiotransform <<'EOF'
y
y
even4
odd4
y
EOF

# 25. rtransition
rtransition > out_transition <<'EOF'
y
y
even4
odd4
E1,M2
EOF

# 26. rtabtrans1
rtabtrans1 <<'EOF'
even4.cm
odd4.cm

12
0
EOF

# 27. rtabtrans2
rtabtrans2 <<'EOF'
even4.odd4.ct
0
1e4
1e-4
y
3
EOF

# 28. lscomp.pl
lscomp.pl <<'EOF'
even4
odd4
n
n
12
EOF

