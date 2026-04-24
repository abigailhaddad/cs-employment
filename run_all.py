import extract
import analysis
import export_web_data

for mod in [extract, analysis, export_web_data]:
    print(f"\n── {mod.__name__} ──")
    mod.main()

print("\nDone.")
