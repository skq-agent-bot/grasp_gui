#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
command -v jj2lsj >/dev/null 2>&1 || jj2lsj() { jj2lsj_2025 "$@"; }
cd .

# 1. rnucleus
rnucleus <<'EOF'
28
61
n
58.6934
1
1
1
EOF

# 2. rcsfgenerate -> Ni_mr.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(1,i)3p(4,i)
2s(2,i)2p(6,i)3s(2,i)3p(2,i)3d(1,i)

3s,3p,3d
1,9
0
y
2s(2,i)2p(6,i)3s(2,i)3p(3,i)

3s,3p
1,5
0
n
EOF
cp rcsf.out Ni_mr.c

# 3. rangular (Ni_mr.c)
cp Ni_mr.c rcsf.inp
rangular <<'EOF'
y
EOF

# 4. rwfnestimate
rwfnestimate <<'EOF'
y
2
*
EOF

# 5. rmcdhf -> Ni_mr
rmcdhf <<'EOF'
y
1-8
1
1-11
1-3
1-10
1
1-5
1-2
5
*
*
999
EOF
rsave Ni_mr

# 6. rcsfgenerate -> Ni_even_mr.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(1,i)3p(4,i)
2s(2,i)2p(6,i)3s(2,i)3p(2,i)3d(1,i)

3s,3p,3d
1,9
0
n
EOF
cp rcsf.out Ni_even_mr.c

# 7. rcsfgenerate -> Ni_even_n4.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(1,*)3p(4,*)
2s(2,i)2p(6,i)3s(2,*)3p(2,*)3d(1,*)

4s,4p,4d,4f
1,9
2
n
EOF
cp rcsf.out Ni_even_n4.c

# 8. rcsfinteract -> Ni_even_n4.c
cp Ni_even_mr.c rcsfmr.inp
cp Ni_even_n4.c rcsf.inp
rcsfinteract <<'EOF'
2
EOF
cp rcsf.out Ni_even_n4.c

# 9. rangular (Ni_even_n4.c)
cp Ni_even_n4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 10. rwfnestimate
rwfnestimate <<'EOF'
y
1
Ni_mr.w
*
2
*
EOF

# 11. rmcdhf -> Ni_even_n4
rmcdhf <<'EOF'
y
1-8
1-11
1-10
1-5
1-2
5
4*

999
EOF
rsave Ni_even_n4

# 12. rci Ni_even_n4
rci <<'EOF'
y
Ni_even_n4
y
n
y
n
n
y
4
1-8
1-11
1-10
1-5
1-2
EOF

# 13. jj2lsj Ni_even_n4
jj2lsj <<'EOF'
Ni_even_n4
y
y
y
EOF

# 14. rcsfgenerate -> Ni_odd_mr.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(2,i)3p(3,i)

3s,3p
1,5
0
n
EOF
cp rcsf.out Ni_odd_mr.c

# 15. rcsfgenerate -> Ni_odd_n4.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)2p(6,i)3s(2,*)3p(3,*)

4s,4p,4d,4f
1,5
2
n
EOF
cp rcsf.out Ni_odd_n4.c

# 16. rcsfinteract -> Ni_odd_n4.c
cp Ni_odd_mr.c rcsfmr.inp
cp Ni_odd_n4.c rcsf.inp
rcsfinteract <<'EOF'
2
EOF
cp rcsf.out Ni_odd_n4.c

# 17. rangular (Ni_odd_n4.c)
cp Ni_odd_n4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 18. rwfnestimate
rwfnestimate <<'EOF'
y
1
Ni_mr.w
*
2
*
EOF

# 19. rmcdhf -> Ni_odd_n4
rmcdhf <<'EOF'
y
1
1-3
1
5
4*

999
EOF
rsave Ni_odd_n4

# 20. rci Ni_odd_n4
rci <<'EOF'
y
Ni_odd_n4
y
n
y
n
n
y
4
1
1-3
1
EOF

# 21. jj2lsj Ni_odd_n4
jj2lsj <<'EOF'
Ni_odd_n4
y
y
y
EOF

# 22. rlevels
rlevels Ni_even_n4.cm Ni_odd_n4.cm > energy4 < /dev/null

# 23. rbiotransform
rbiotransform > out_rbiotransform <<'EOF'
y
y
Ni_odd_n4
Ni_even_n4
y
EOF

# 24. rtransition
rtransition > out_transition <<'EOF'
y
y
Ni_odd_n4
Ni_even_n4
E1
EOF

