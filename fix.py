import re
with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()
# Replace the import with an inline dictionary definition, preserving indentation
text = re.sub(
    r'(\s+)from awg_manager import CONTAINER_NAMES as AWG_CONTAINER_NAMES\n\s+container = AWG_CONTAINER_NAMES\.get\((.*?), f\'amnezia-\{.*?\.replace\("_", "-"\)\}\)',
    r"\1AWG_CONTAINER_NAMES = {'awg_legacy': 'amnezia-awg-legacy', 'awg2': 'amnezia-awg2'}\n\1container = AWG_CONTAINER_NAMES.get(\2, f'amnezia-{\2.replace(\"_\", \"-\")}')",
    text
)
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)
