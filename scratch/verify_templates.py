import os
from jinja2 import Environment, FileSystemLoader

templates_dir = r"c:\Users\lukit\Downloads\POLMAN TERBAIK\Semester 5\BIG DATA\dmp_store_project\templates"
env = Environment(loader=FileSystemLoader(templates_dir))

errors = []
for fname in os.listdir(templates_dir):
    if fname.endswith(".html"):
        try:
            env.get_template(fname)
            print(f"OK: {fname}")
        except Exception as e:
            print(f"ERROR in {fname}: {e}")
            errors.append((fname, str(e)))

if not errors:
    print("\nALL TEMPLATES COMPILED SUCCESSFULLY!")
else:
    print(f"\n{len(errors)} TEMPLATES HAVE ERRORS!")
