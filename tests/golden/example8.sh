#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
cd .

# 1. rnucleus
rnucleus <<'EOF'
4
9
n
9
1
1
1
EOF

# 2. rcsfgenerate -> DF.c
rcsfgenerate <<'EOF'
*
1
2s(2,i)
2p(2,i)

2s,2p
0,0
0
n
EOF
cp rcsf.out DF.c

# 3. rangular (DF.c)
cp DF.c rcsf.inp
rangular <<'EOF'
y
EOF

# 4. rwfnestimate
rwfnestimate <<'EOF'
y
2
*
EOF

# 5. rmcdhf_mem -> DF
rmcdhf_mem <<'EOF'
y
1
*
*
100
EOF
rsave DF

# 6. rcsfgenerate -> n3.c
rcsfgenerate <<'EOF'
*
1
2s(2,*)

3s,3p,3d
0,0
2
n
EOF
cp rcsf.out n3.c

# 7. rangular (n3.c)
cp n3.c rcsf.inp
rangular <<'EOF'
y
EOF

# 8. rwfnestimate
rwfnestimate <<'EOF'
y
1
DF.w
*
2
*
EOF

# 9. rmcdhf_mem -> n3
rmcdhf_mem <<'EOF'
y
1
3*

100
EOF
rsave n3

# 10. rcsfgenerate -> n4.c
rcsfgenerate <<'EOF'
*
1
2s(2,*)

4s,4p,4d,4f
0,0
2
n
EOF
cp rcsf.out n4.c

# 11. rangular (n4.c)
cp n4.c rcsf.inp
rangular <<'EOF'
y
EOF

# 12. rwfnestimate
rwfnestimate <<'EOF'
y
1
n3.w
*
4
*
5
EOF

# 13. rmcdhf_mem -> n4
rmcdhf_mem <<'EOF'
y
1
4*

100
EOF
rsave n4

# 14. rci n4
rci <<'EOF'
y
n4
y
n
y
n
n
y
3
1
EOF

# 15. rmixextract
rmixextract > mix4 <<'EOF'
0
n4
y
0
n
EOF

# 16. rdensity
rdensity <<'EOF'
y
n4
y
2
EOF

# 17. cp
cp n4.c n4NO.c < /dev/null

# 18. cp
cp n4.nw n4NO.w < /dev/null

# 19. rci n4NO
rci <<'EOF'
y
n4NO
y
n
y
n
n
y
3
1
EOF

# 20. rmixextract
rmixextract > mix4NO <<'EOF'
0
n4NO
y
0
n
EOF

