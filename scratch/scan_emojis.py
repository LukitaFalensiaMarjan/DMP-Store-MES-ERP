import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

template_dir = 'templates'
for fname in sorted(os.listdir(template_dir)):
    if fname.endswith('.html'):
        fpath = os.path.join(template_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            emojis = []
            for ch in line:
                cp = ord(ch)
                if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0x2300 <= cp <= 0x23FF) or (0x2B50 <= cp <= 0x2B55) or cp in [0x2714, 0x2716, 0x2705, 0x274C, 0x2702, 0x2708, 0x2709, 0x270F, 0x2712, 0x271D, 0x2721, 0x2728, 0x2733, 0x2734, 0x2744, 0x2747, 0x274E, 0x2753, 0x2754, 0x2755, 0x2757, 0x2763, 0x2764, 0x2795, 0x2796, 0x2797, 0x27A1, 0x27B0, 0x27BF]:
                    emojis.append(f"\\u{cp:04x}")
            if emojis:
                clean_line = line.strip().encode('ascii', 'replace').decode('ascii')
                print(f"{fname}:{idx+1}: {' '.join(emojis)} -> {clean_line[:90]}")

