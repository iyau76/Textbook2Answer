import re

s = r"""\begin{equation}
\frac{\lambda - 2(|M|+1)}{4} = n_r, \quad (n_r = 0, 1, 2, \dots)
\label{eq:6-3-3-8}
\end{equation}"""

math_pattern = r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\begin\{equation\}.*?\\end\{equation\}|\\begin\{align\*?\}.*?\\end\{align\*?\}|\\begin\{cases\}.*?\\end\{cases\})"

parts = re.split(math_pattern, s, flags=re.DOTALL)

for i in range(len(parts)):
    if i % 2 == 0:
        print(f"TEXT MODE [{i}]:", repr(parts[i]))
    else:
        print(f"MATH MODE [{i}]:", repr(parts[i]))
