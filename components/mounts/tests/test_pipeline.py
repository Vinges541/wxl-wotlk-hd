import copy,json,os,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from wxl_mounts.geometry import compare_meshes
from wxl_mounts.closure import required_members
from wxl_mounts.exports import RawIndex
from wxl_mounts.tables import patch_mounts,TABLES
from wxl_mounts.creatures import DBC
from wxl_mounts.druids import DISPLAY_IDS,BUILD_CONFIG,patch_tables
from wxl_mounts.planning import selected_geosets,export_request
from wxl_mounts.packing import sha,digest
from wxl_mounts.animations import lookup_slot,runtime_state,repair_missing_remaps,sequence_tables,unreachable_runtime_ids,buckets
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'races/tests'))
import test_druid_forms
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import install_creatures as deploy

class GeometryTests(unittest.TestCase):
    def test_storage_order_winding_and_uniform_coordinates_are_not_upgrades(self):
        old=[((0.,0.,0.),(1.,0.,0.),(0.,1.,1.)),((0.,0.,0.),(0.,1.,1.),(0.,0.,1.))]
        reordered=[tuple(reversed(t)) for t in reversed(old)]
        self.assertFalse(compare_meshes(old,reordered)['changed'])
        transformed=[tuple(tuple(2*x+3 for x in p) for p in t) for t in old]
        self.assertFalse(compare_meshes(old,transformed)['changed'])
        # A new LOD elsewhere cannot affect this explicit primary surface list.
        changed=copy.deepcopy(old);changed.append(((0.,0.,0.),(1.,0.,0.),(2.,2.,2.)))
        self.assertTrue(compare_meshes(old,changed)['changed'])
    def test_explicit_empty_geosets_differ_from_default(self):
        self.assertEqual(selected_geosets({'ID':864},{'CreatureGeosetDataID':768},[]),[])
        self.assertIsNone(selected_geosets({'ID':864},{'CreatureGeosetDataID':0},[]))
        self.assertEqual(selected_geosets({'ID':1},{'CreatureGeosetDataID':3},[{'CreatureDisplayInfoID':1,'GeosetIndex':1,'GeosetValue':2}]),[202])
    def test_runtime_closure_is_derived_from_m2(self):
        body=bytearray(0x140);body[:4]=b'MD20';struct.pack_into('<I',body,68,1)
        chunk=lambda tag,b:tag+struct.pack('<I',len(b))+b
        model=chunk(b'MD21',body)+chunk(b'SFID',struct.pack('<3I',20,21,22))+chunk(b'AFID',struct.pack('<HHI',4,0,30))
        self.assertEqual(required_members('WXL/ModernMounts/Models/1/Mount.m2',model),{
            'WXL/ModernMounts/Models/1/Mount00.skin','WXL/ModernMounts/Models/1/Mount_lod01.skin',
            'WXL/ModernMounts/Models/1/Mount_lod02.skin','WXL/ModernMounts/Models/1/Mount0004-00.anim'})
        bad=model+chunk(b'AFID',struct.pack('<HHI',4,0,31))
        with self.assertRaises(ValueError):required_members('M.m2',bad)

class AnimationHashTests(unittest.TestCase):
    def model(self,ids):
        body=bytearray(0x140+64*len(ids));body[:4]=b'MD20'
        struct.pack_into('<II',body,28,len(ids),0x140)
        lookup=[-1]*11
        for slot,aid in enumerate(ids):
            at=0x140+slot*64;struct.pack_into('<H',body,at,aid)
            struct.pack_into('<I',body,at+12,0x20);struct.pack_into('<h',body,at+60,-1)
            for bucket in buckets(aid,len(lookup)):
                if lookup[bucket]==-1:lookup[bucket]=slot;break
        at=len(body);body.extend(struct.pack('<11h',*lookup));struct.pack_into('<II',body,36,len(lookup),at)
        return b'MD21'+struct.pack('<I',len(body))+body+b'TEST'+struct.pack('<I',4)+b'tail'
    def test_native_collisions_and_runtime_replacement_keep_preferred_slot(self):
        ids=[0]*15;ids[4]=540;ids[5]=542;ids[14]=5
        lookup=[-1]*67;lookup[5]=4;lookup[6]=5;lookup[10]=14
        self.assertEqual(lookup_slot(ids,lookup,5),14)
        ids=[0]*58;ids[23]=562;ids[56]=534;ids[57]=45
        lookup=[-1]*163;lookup[45]=56;lookup[46]=57
        ids,lookup=runtime_state(ids,lookup)
        self.assertEqual(lookup_slot(ids,lookup,45),23)
    def test_missing_remap_rehash_preserves_flying_variant_and_payload(self):
        before=self.model([0,41,548,556])
        self.assertEqual(unreachable_runtime_ids(before),[42])
        after,report=repair_missing_remaps(before)
        self.assertEqual(report['remaps'],[{'sequenceSlot':3,'fromId':556,'toId':42}])
        self.assertEqual(unreachable_runtime_ids(after),[])
        _,_,_,ids,lookup=sequence_tables(after);ids,lookup=runtime_state(ids,lookup)
        self.assertEqual(lookup_slot(ids,lookup,41),2) # Keep flying variant, not earlier swimming slot1.
        self.assertEqual(lookup_slot(ids,lookup,42),3)
        self.assertEqual(after[-12:],before[-12:])
        _,oldbody,offset,_,_=sequence_tables(before);_,newbody,_,_,_=sequence_tables(after)
        allowed=set(range(36,44))|set(range(offset+3*64,offset+3*64+2))
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(oldbody,newbody))))
        self.assertEqual(repair_missing_remaps(after),(after,{}))
        external=before+b'AFID'+struct.pack('<IHHI',8,556,0,99)
        with self.assertRaises(ValueError):repair_missing_remaps(external)
    def test_valid_hash_is_untouched(self):
        original=self.model([0,41,548])
        self.assertEqual(repair_missing_remaps(original),(original,{}))

class CombinedTableTests(unittest.TestCase):
    def test_tauren_scale_preserves_composed_druids_and_mounts(self):
        from wxl_races.tauren_scale import apply_world_scale
        fixture=test_druid_forms.DruidFormsTests();fixture.setUp()
        models=DBC(fixture.b,28)
        for i,sex in enumerate(('Male','Female'),100):
            row=[0]*28;row[0]=i;row[4]=0x3f800000
            row[2]=models.add_string(f'Character/Tauren/{sex}/Tauren{sex}.m2');models.rows.append(row)
        fixture.b=models.encode();originals={TABLES[0]:fixture.a,TABLES[1]:fixture.b}
        baseline=patch_tables(fixture.a,fixture.b,fixture.plan())
        plan={'schemaVersion':1,'kind':'wxl-mount-replacement-plan','build':{'BuildConfig':BUILD_CONFIG},
              'sourceHashes':{k:sha(v) for k,v in originals.items()},'displays':[{'displayId':50000,'legacyModelId':25,'approved':True,'modelPath':'WXL/ModernMounts/Models/50000/Mount.m2'}]}
        composed=patch_mounts(originals,baseline,plan)
        before=DBC(composed[TABLES[1]],28)
        scaled=apply_world_scale(fixture.b,composed[TABLES[1]])
        after=DBC(scaled,28)
        for row in before.rows:
            expected=row.copy()
            if row[0] in (100,101):expected[4]=0x3f400000
            self.assertEqual(after.by_id[row[0]],expected)
        self.assertEqual(apply_world_scale(fixture.b,scaled),scaled)

    def test_all_druids_and_originals_survive_mount_merge(self):
        fixture=test_druid_forms.DruidFormsTests();fixture.setUp();originals={TABLES[0]:fixture.a,TABLES[1]:fixture.b}
        baseline=patch_tables(fixture.a,fixture.b,fixture.plan())
        plan={'schemaVersion':1,'kind':'wxl-mount-replacement-plan','build':{'BuildConfig':BUILD_CONFIG},
              'sourceHashes':{k:sha(v) for k,v in originals.items()},'displays':[{'displayId':50000,'legacyModelId':25,'approved':True,'modelPath':'WXL/ModernMounts/Models/50000/Mount.m2'}]}
        result=patch_mounts(originals,baseline,plan);a=DBC(result[TABLES[0]],16);b=DBC(result[TABLES[1]],28)
        prior_a=DBC(baseline[TABLES[0]],16);prior_b=DBC(baseline[TABLES[1]],28)
        for did in DISPLAY_IDS|{100}:self.assertEqual(a.by_id[did],prior_a.by_id[did])
        self.assertEqual(b.rows[:-1],prior_b.rows);self.assertEqual(a.by_id[50000][2:],prior_a.by_id[50000][2:])
        self.assertEqual(b.rows[-1][3:],prior_b.by_id[25][3:])
        for change in ('duplicate','path','source','druid'):
            bad=copy.deepcopy(plan)
            if change=='duplicate':bad['displays']*=2
            if change=='path':bad['displays'][0]['modelPath']='Character/Human.m2'
            if change=='source':bad['sourceHashes'][TABLES[0]]='0'*64
            if change=='druid':bad['displays'][0]['displayId']=864
            with self.assertRaises(ValueError):patch_mounts(originals,baseline,bad)

class RawExportTests(unittest.TestCase):
    def test_explicit_index_requires_pinned_complete_files_and_conflict_free_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            for folder in (a,b):
                (folder/'10.m2').write_bytes(b'MD21synthetic')
                (folder/'10.files.manifest.json').write_text(json.dumps({'files':[{'type':'M2','fileDataID':10,'file':str(folder/'10.m2')}]}))
                (folder/'status.json').write_text(json.dumps({'state':'complete','build':{'BuildConfig':BUILD_CONFIG,'Product':'wow'},'models':[{'fileDataId':10,'state':'complete'}],'files':[]}))
            self.assertIsNotNone(RawIndex([a,b],BUILD_CONFIG).resolve_fdid(10))
            (b/'10.m2').write_bytes(b'conflicting')
            with self.assertRaises(ValueError):RawIndex([a,b],BUILD_CONFIG)
            (a/'10.files.manifest.json').write_text(json.dumps({'files':[{'type':'M2','fileDataID':10,'file':str(b/'10.m2')}]}))
            with self.assertRaises(ValueError):RawIndex([a],BUILD_CONFIG)

class InstallTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name).resolve();self.client=self.root/'client';self.package=self.root/'package';self.client.mkdir();self.package.mkdir()
        self.rows=[]
        for name in (deploy.ARCHIVE,deploy.DLL_PATH):
            p=self.package/name;p.parent.mkdir(parents=True);p.write_bytes(name.encode());self.rows.append({'path':name,'size':p.stat().st_size,'sha256':digest(p)})
        (self.package/'release-manifest.json').write_text('{}')
        old={}
        for name in (deploy.OLD_ARCHIVE,deploy.OLD_DLL):
            p=self.client/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('old '+name).encode());old[name]=digest(p)
        (self.client/'WTF').mkdir();(self.client/'WTF/Config.wtf').write_text('keep exact config');(self.client/'Data/Patch-Other.MPQ').write_bytes(b'keep exact other patch')
        for mock in (patch.object(deploy,'OLD_FILES',old),patch.object(deploy,'check_runtime'),patch.object(deploy,'originals',return_value={}),
                     patch.object(deploy,'verify',return_value={'files':self.rows,'druids':True}),patch.object(deploy,'check_overlays',return_value={self.client/'Data/Patch-Other.MPQ':digest(self.client/'Data/Patch-Other.MPQ')}),patch.object(deploy,'require_wow_closed')):
            mock.start();self.addCleanup(mock.stop)
    def test_preview_install_idempotence_and_single_redirect_order(self):
        self.assertEqual(len(deploy.install(self.package,self.client,None)['changes']['add']),2)
        seen=[];original_link=os.link
        def publish(source,target):
            seen.append(Path(target).relative_to(self.client).as_posix())
            if str(target).endswith('.dll'):
                self.assertFalse((self.client/deploy.OLD_DLL).exists());self.assertTrue((self.client/deploy.ARCHIVE).exists())
            return original_link(source,target)
        with patch.object(deploy.os,'link',side_effect=publish):r=deploy.install(self.package,self.client,None,True,True,self.root/'report.json')
        self.assertEqual(seen,[deploy.ARCHIVE,deploy.DLL_PATH]);self.assertEqual(r['state'],'complete');self.assertEqual(r['preservedBefore'],r['preservedAfter'])
        self.assertEqual((self.client/'WTF/Config.wtf').read_text(),'keep exact config');self.assertFalse((self.client/deploy.OLD_ARCHIVE).exists())
        self.assertEqual(deploy.install(self.package,self.client,None)['changes'],{'add':[],'remove':[]})
    def test_resume_after_archive_publication_without_two_dlls(self):
        link=os.link
        def fail_dll(source,target):
            if str(target).endswith('.dll'):raise OSError('synthetic interruption')
            return link(source,target)
        with patch.object(deploy.os,'link',side_effect=fail_dll):
            with self.assertRaises(OSError):deploy.install(self.package,self.client,None,True,True,self.root/'interrupted.json')
        self.assertTrue((self.client/deploy.ARCHIVE).exists());self.assertFalse((self.client/deploy.DLL_PATH).exists());self.assertFalse((self.client/deploy.OLD_DLL).exists())
        r=deploy.install(self.package,self.client,None,True,True,self.root/'resumed.json');self.assertEqual(r['state'],'complete')
    def test_running_wow_unknown_files_and_links_refused(self):
        with patch.object(deploy,'require_wow_closed',side_effect=ValueError('running')):
            with self.assertRaises(ValueError):deploy.install(self.package,self.client,None,True,True,self.root/'running.json')
        self.assertFalse((self.client/deploy.ARCHIVE).exists())
        p=self.client/deploy.ARCHIVE;p.write_bytes(b'unknown')
        with self.assertRaises(ValueError):deploy.install(self.package,self.client,None)
        self.assertEqual(p.read_bytes(),b'unknown');p.unlink();p.symlink_to(self.package/deploy.ARCHIVE)
        with self.assertRaises(ValueError):deploy.install(self.package,self.client,None)

class LocaleInputTests(unittest.TestCase):
    def test_active_locale_precedes_stock_global_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'WTF').mkdir();(root/'WTF/Config.wtf').write_text('SET locale "ruRU"\n')
            for name in ('Data/ruRU/patch-ruRU-3.MPQ','Data/ruRU/locale-ruRU.MPQ','Data/enGB/locale-enGB.MPQ','Data/patch-3.MPQ'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
            with patch.object(deploy,'Reader') as reader:
                reader.return_value.read.return_value=(b'dbc','source')
                self.assertEqual(deploy.originals(root,None),{name:b'dbc' for name in TABLES})
                paths=reader.call_args.args[1]
                self.assertEqual([p.name for p in paths],['patch-ruRU-3.MPQ','locale-ruRU.MPQ','patch-3.MPQ'])
                reader.return_value.close.assert_called_once()
            (root/'WTF/Config.wtf').write_text('')
            with self.assertRaises(ValueError):deploy.originals(root,None)

if __name__=='__main__':unittest.main()
