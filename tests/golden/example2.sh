#!/bin/sh
set -x

export PATH=/opt/grasp/bin:$PATH
cd .

# 1. rnucleus
rnucleus <<'EOF'
5
11
n
10.81
1.5
2.6886489
1
EOF

# 2. rcsfgenerate -> 2s2p_DF.c
rcsfgenerate <<'EOF'
*
0
1s(2,i)2s(1,i)2p(1,i)

2s,2p
0,4
0
n
EOF
cp rcsf.out 2s2p_DF.c

# 3. rangular (2s2p_DF.c)
cp 2s2p_DF.c rcsf.inp
rangular <<'EOF'
y
EOF

# 4. hf
hf <<'EOF'
B,AV,5.
  1s
2s(1)2p(1)
all
y
y
n
n
EOF

# 5. cp
cp wfn.out wfn.inp < /dev/null

# 6. rwfnmchfmcdf
rwfnmchfmcdf < /dev/null

# 7. cp
cp rwfn.out rwfn.inp < /dev/null

# 8. rmcdhf -> 2s2p_DF
rmcdhf <<'EOF'
y
1
1,2
1
5
*
*
100
EOF
rsave 2s2p_DF

# 9. jj2lsj 2s2p_DF
jj2lsj <<'EOF'
2s2p_DF
n
y
y
EOF

# 10. rlevels
rlevels 2s2p_DF.m > energyDF < /dev/null

# 11. rtablevels
rtablevels <<'EOF'
0
1
energyDF
EOF

