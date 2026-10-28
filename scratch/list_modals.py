import os
import re

template_dir = 'templates'
for fname in sorted(os.listdir(template_dir)):
    if fname.endswith('.html'):
        fpath = os.path.join(template_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        modals = re.findall(r'<div[^>]*id=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*modal[^"\']*["\']', content)
        # Also try reverse attribute order: class before id
        modals += re.findall(r'<div[^>]*class=["\'][^"\']*modal[^"\']*["\'][^>]*id=["\']([^"\']+)["\']', content)
        if modals:
            print(f"{fname}: {list(set(modals))}")
