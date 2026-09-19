import struct,unittest
from wxl_races.tauren_scale import apply_world_scale
from wxl_races.druids import DBC

def fixture():
    names=['Character\\Tauren\\Male\\TaurenMale.mdx','Character\\Tauren\\Female\\TaurenFemale.mdx','Character\\Human\\Male\\HumanMale.mdx']
    strings=b'\0';rows=[]
    for i,name in enumerate(names,1):
        row=[0]*28;row[0]=i;row[2]=len(strings);row[4]=struct.unpack('<I',struct.pack('<f',2 if i==2 else 1))[0]
        strings+=name.encode()+b'\0';rows.append(row)
    return b'WDBC'+struct.pack('<4I',3,28,112,len(strings))+b''.join(struct.pack('<28I',*r) for r in rows)+strings

class TaurenScaleTests(unittest.TestCase):
    def test_both_sexes_only_scale_field_and_idempotent(self):
        original=fixture();result=apply_world_scale(original,original)
        a,b=DBC(original,28),DBC(result,28)
        for old,new in zip(a.rows,b.rows):
            if old[0] in (1,2):
                self.assertEqual(old[:4]+old[5:],new[:4]+new[5:])
                self.assertEqual(struct.unpack('<f',struct.pack('<I',new[4]))[0],.75 if old[0]==1 else 1.5)
            else:self.assertEqual(old,new)
        self.assertEqual(a.strings,b.strings)
        self.assertEqual(apply_world_scale(original,result),result)
    def test_preserves_added_creature_rows(self):
        original=fixture();table=DBC(original,28);row=table.rows[2].copy();row[0]=100
        row[2]=table.add_string('WXL/DruidForms/Models/892/Form.m2');table.rows.append(row)
        result=DBC(apply_world_scale(original,table.encode()),28)
        self.assertEqual(result.by_id[100],row)
    def test_conflicting_scale_and_missing_sex_refused(self):
        original=fixture();table=DBC(original,28);table.rows[0][4]=0x40000000
        with self.assertRaises(ValueError):apply_world_scale(original,table.encode())
        table=DBC(original,28);table.rows.pop(1)
        with self.assertRaises(ValueError):apply_world_scale(table.encode(),table.encode())
