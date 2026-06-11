import sqlite3, json
conn = sqlite3.connect(r'd:\数字分身\backend\data\digital_twin.db')
row = conn.execute("SELECT config_json FROM personas WHERE slug=?", ("default",)).fetchone()
config = json.loads(row[0])
tmpl = config.get('system_prompt_template', '')
idx = tmpl.find('knowledge')
print(tmpl[idx:idx+500] if idx > 0 else 'NOT FOUND')
conn.close()
