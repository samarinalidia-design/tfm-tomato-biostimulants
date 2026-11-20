"""Observable regressions and schema-validated end-to-end synthetic source test.
No real articles are changed and no LLM extraction accuracy is implied.
"""
from __future__ import annotations
import copy,csv,hashlib,json,math,os,shutil,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
import yaml
from openpyxl import Workbook,load_workbook
import fitz
PKG=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PKG/'tools'))
from tfmlib.config import Config
from tfmlib.db import connect,init_schema,rows,tx,sha256_file
from tfmlib.importer import import_workbook,seed_studies
from tfmlib.tasks import seed_triage,claim,create_task
from tfmlib.sourceqa import index_sources,view
from tfmlib.submit import submit,ROB_DOMAINS
from tfmlib.contrasts import build,dependency_clusters
from tfmlib.export import build_frames,export_all
from tfmlib.release import human_audit_export,human_audit_import,checks,snapshot_hash

class Env:
 def __init__(self):
  self.tmp=Path(tempfile.mkdtemp(prefix='tfm_v2_',dir=PKG.parent));self.root=self.tmp/'pkg'
  shutil.copytree(PKG,self.root,ignore=shutil.ignore_patterns('db','work','exports','.venv','.git','__pycache__','*.pyc','tfm_v2_*'))
  self.data=self.tmp/'data';self.data.mkdir();self.src=self.data/'01_fulltext';self.src.mkdir();self.supp=self.data/'02_supplements';self.supp.mkdir()
  c=yaml.safe_load((self.root/'config/pipeline.yaml').read_text());c['scope']['expected_count']=2
  (self.root/'config/pipeline.yaml').write_text(yaml.safe_dump(c))
  with (self.root/'manifests/scope_A_399.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['study_id']);w.writeheader();w.writerows([{'study_id':'112'},{'study_id':'126'}])
  self.sources=[{'study_id':s,'role':'FULLTEXT','active_file_id':'SOURCE_'+s,'active_file_name':s+'.pdf'} for s in ('112','126')]+[{'study_id':'112','role':'SUPPLEMENT','active_file_id':'SUPP_112','active_file_name':'112_supp.pdf'}]
  with (self.root/'manifests/source_manifest_A_462.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=self.sources[0].keys());w.writeheader();w.writerows(self.sources)
  for s in self.sources:
   p=(self.src if s['role']=='FULLTEXT' else self.supp)/s['active_file_name']
   pdf=fitz.open();pg=pdf.new_page();pg.insert_text((45,50),'Synthetic ORIGINAL source. Table 1 total fresh fruit yield, kg/plant, cumulative.\nC 1.1 +/- 0.1, S 1.0 +/- 0.1, B 1.3 +/- 0.1, SB 1.2 +/- 0.1.\nn=4 independent plots, randomized factorial design; final harvest.\nMixed units test: S 1000 g/plant +/-100, SB 1.2 kg/plant +/-0.1.\nSupplement contains irrelevant omics metadata only, no agronomic targets.',fontsize=9)
   for j,val in enumerate((0,1,2)):
    y=400-100*val;pg.draw_line((40,y),(46,y));pg.insert_text((18,y),str(val),fontsize=8)
   for j,mean in enumerate((1.1,1.0,1.3,1.2)):
    x=70+j*45;yp=400-100*mean;pg.draw_rect(fitz.Rect(x,yp,x+20,400));pg.draw_line((x+10,yp),(x+10,yp-10));pg.draw_line((x+5,yp-10),(x+15,yp-10))
   pdf.save(p);pdf.close()
  wb=Workbook();wb.remove(wb.active)
  data={
   'studies':[['study_id','doi','title','authors','year','publication_type','dataset_role','first_publication_date','temporal_eligibility','class_final'],['112','10.fake/112','Tomato yield under salt','A',2023,'journal-article','TRAIN_DEV',None,'ELIGIBLE_KNOWN_PRE2024','A'],['126','10.fake/126','Tomato yield under drought','B',2022,'journal-article','TRAIN_DEV',None,'ELIGIBLE_KNOWN_PRE2024','A']],
   'files':[['file_key','study_id','role','active_file_id','active_file_name','mime_type']]+[[f'F{i}',r['study_id'],r['role'],r['active_file_id'],r['active_file_name'],'application/pdf'] for i,r in enumerate(self.sources)],
   'experiments':[['experiment_id','study_id','cultivar','system'],['E112','112','G','greenhouse'],['E126','126','G','greenhouse']],
   'arms':[['arm_id','experiment_id','arm_label','arm_role','stress_level']]+[[s+'_'+a,'E'+s,a,'',''] for s in ('112','126') for a in ('C','S','B','SB')],
   'measurements':[['measurement_id','experiment_id','arm_id','outcome_standard_name','mean','sd','se','n','unit_raw','provenance_id']],
   'outcome_dictionary':[['outcome_standard_name','target_role'],['fruit_yield','PRIMARY_YIELD']],
   'study_relations':[['relation_id','study_id_a','study_id_b','relation_type']],
   'provenance_qa':[['provenance_id','entity_id','source_file_id']],
  }
  for n,data_rows in data.items():
   ws=wb.create_sheet(n)
   for row in data_rows:ws.append(row)
  self.wb=self.data/'TFM_DATABASE_CLASS_A_WORKING.xlsx';wb.save(self.wb)
  (self.root/'config/paths.yaml').write_text(yaml.safe_dump({'workbook':str(self.wb),'fulltext_root':str(self.src),'supplements_root':str(self.supp),'docling_root':str(self.data/'docling')}))
  self.cfg=Config(self.root);self.con=connect(self.cfg.db_path);init_schema(self.con)
  import_workbook(self.con,self.wb);seed_studies(self.con,self.cfg);index_sources(self.con,self.cfg)
  self.receipts={r['active_file_id']:view(self.con,self.cfg,r['active_file_id'],page=1)['receipt_id'] for r in self.sources}
 def close(self):self.con.close();shutil.rmtree(self.tmp,ignore_errors=True)
 def task(self,tt,s=None):
  r=claim(self.con,self.cfg,'test','any',[tt],1,s)
  assert r,tt
  return r[0]
 def hdr(self,t):return {'task_id':t['task_id'],'study_id':t['study_id'],'agent':t['agent'],'model_id':'SYNTHETIC_TEST_NO_MODEL'}
 def submit(self,t,d,expected='ACCEPTED'):
  p=self.root/'work/outbox'/f"{t['task_id']}.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d))
  r=submit(self.con,self.cfg,t['task_id'],p)
  assert r['status']==expected,r
  return r
 def triage(self,t):
  s=t['study_id'];fid='SOURCE_'+s
  sources=[r for r in self.sources if r['study_id']==s]
  return {**self.hdr(t),'pass':'P1','scope':{'class_A_ok':True,'flag':'NONE'},'design':{'n_experiments':1,'summary':'2x2 independent randomized factorial tomato experiment','has_C':'YES','has_S':'YES','has_B':'YES','has_SB':'YES','has_AxB':'NO','stress_domains':['SALINITY'],'system':'greenhouse'},'targets':{'fruit_yield':'PRESENT','dry_biomass':'ABSENT','yield_components':'ABSENT'},'slots':[{'endpoint':'FRUIT_YIELD','source_kind':'TABLE','source_file_id':fid,'locator_label':'Table 1','page':1,'expected_n_values':4,'has_dispersion':'YES','description':'cumulative total fresh fruit yield, 4 arms'}],'negative_evidence':{'sections_read':['Methods','Results'],'tables_checked':['Table 1'],'figures_checked':[],'supplements_checked':['112_supp.pdf'] if s=='112' else [],'search_terms':['yield','fruit','harvest','biomass','dry weight']},'source_checks':[{'source_file_id':r['active_file_id'],'disposition':'IRRELEVANT' if r['role']=='SUPPLEMENT' else 'CHECKED','receipt_ids':[self.receipts[r['active_file_id']]],'docling_findings':'UNVERIFIED; checked original source; no inherited QA status','relevance':'omics pointer only' if r['role']=='SUPPLEMENT' else 'target table and Methods'} for r in sources],'asset_inventory':[{'asset_key':'T1','source_file_id':fid,'locator':'Table 1','relevance':'TARGET','disposition':'SLOT','reason':'primary target'}]}
 def design(self,t,patch=False):
  s=t['study_id'];als=[('C','NONE','NONE'),('S','S1','NONE'),('B','NONE','B1'),('SB','S1','B1')]
  return {**self.hdr(t),'experiments':[{'experiment_key':'E1','experiment_id':'E'+s,'description':'verified 2x2 randomized independent factorial','system':'greenhouse','allocation':'INDEPENDENT_PARALLEL','factorial_verified':True}], 'arms':[{'arm_key':'E1.'+a,'experiment_key':'E1','arm_id':s+'_'+a,'label_in_source':a,'stress_code':st,'bio_code':b,'n_bio_components':0 if b=='NONE' else 1,'genotype':'G','component_codes':[] if b=='NONE' else ['B1@dose1'],'background_key':'COMMON'} for a,st,b in als], 'timepoints':[{'timepoint_key':'H_TOT','experiment_key':'E1','label':'final cumulative harvest','kind':'HARVEST_CUMULATIVE','is_terminal':True}],'core_patches':[{'table':'arms','row_id':s+'_S','field':'stress_level','current':'','proposed':'100 mM','reason':'original Methods explicitly report this stress','locator':'p1 Methods'}] if patch else []}
 def values(self,t,mixed=False):
  s=t['study_id'];pa='A' if t['task_type']=='EXTRACT_A' else 'B';fid='SOURCE_'+s;slot=rows(self.con,'SELECT slot_id FROM wf_target_slots WHERE study_id=?',(s,))[0]['slot_id']
  vals=[]
  for a,mean in [('C',1.1),('S',1.),('B',1.3),('SB',1.2)]:
   m=1000 if mixed and a=='S' else mean;sd=100 if mixed and a=='S' else .1;unit='g/plant' if mixed and a=='S' else 'kg/plant'
   vals.append({'slot_id':slot,'arm_key':'E1.'+a,'endpoint':'FRUIT_YIELD','yield_scope':'TOTAL','mass_basis':'FRESH','denominator':'PER_PLANT','harvest_window':'CUMULATIVE','timepoint_key':'H_TOT','mean':m,'dispersion_type':'SD','dispersion_value':sd,'n':4,'n_unit':'plots','n_source':'original p1 legend','unit_raw':unit,'source_kind':'TABLE','source_file_id':fid,'page':1,'locator':'Table 1 row '+a+' total fruit yield','verbatim':f'{m} ± {sd}','confidence':'HIGH','receipt_id':self.receipts[fid],'source_cell':'Table 1; row '+a+'; total fresh fruit yield; cumulative; n=4 independent plots'})
  return {**self.hdr(t),'pass':pa,'values':vals,'slot_status':[{'slot_id':slot,'status':'EXTRACTED','n_values':4}],'design_gaps':[]}
 def prepare(self,patch=False,mixed=False):
  seed_triage(self.con,self.cfg)
  for s in ('112','126'):
   t=self.task('TRIAGE',s);self.submit(t,self.triage(t));t=self.task('DESIGN',s);self.submit(t,self.design(t,patch and s=='112'))
   for tt in ('EXTRACT_A','EXTRACT_B'):
    t=self.task(tt,s);self.submit(t,self.values(t,mixed))
   t=self.task('MODERATORS',s);self.submit(t,{**self.hdr(t),'moderators':[{'experiment_key':'E1','arm_key':'E1.SB','feature':'dose','value':1,'unit':'mL/L','locator':'p1 Methods','verbatim':'dose 1 mL/L','availability':'PLAN_PRE_EXPERIMENT','source_file_id':'SOURCE_'+s,'receipt_id':self.receipts['SOURCE_'+s]}],'not_reported':[]})
   t=self.task('ROB',s);self.submit(t,{**self.hdr(t),'assessments':[{'domain':d,'judgement':'unclear','support':'Synthetic original source, no unsupported low-risk inference','locator':'p1 Methods'} for d in ROB_DOMAINS]})
   t=self.task('MODERATORS_VERIFY',s);self.submit(t,{**self.hdr(t),'moderators':[{'experiment_key':'E1','arm_key':'E1.SB','feature':'dose','value':1,'unit':'mL/L','locator':'p1 Methods','verbatim':'dose 1 mL/L','availability':'PLAN_PRE_EXPERIMENT','source_file_id':'SOURCE_'+s,'receipt_id':self.receipts['SOURCE_'+s]}],'not_reported':[]})
  build(self.con,self.cfg)

class RegressionTests(unittest.TestCase):
 def setUp(self):self.e=Env()
 def tearDown(self):self.e.close()
 def test_end_to_end_source_to_atomic_ready_release(self):
  e=self.e;e.prepare(mixed=True)
  self.assertEqual(e.con.execute('SELECT COUNT(*) FROM an_target_values').fetchone()[0],8)
  effects=rows(e.con,"SELECT effect FROM an_contrasts WHERE contrast_type='SB_vs_S'")
  self.assertTrue(all(abs(x['effect']-math.log(1.2))<1e-12 for x in effects))
  self.assertIn('f_dose_unit',build_frames(e.con,e.cfg)['evidence_long'].columns)
  # Persisted closure, and a real user-entered synthetic human form for test purposes only.
  e.con.execute("UPDATE wf_study_status SET state='CLOSED',locked=1")
  out=e.root/'work/human_review/audit.csv';r=human_audit_export(e.con,e.cfg,out)
  self.assertEqual(r['k'],r['N_retained_contrasts'])
  with out.open(encoding='utf-8-sig',newline='') as f:data=list(csv.DictReader(f));cols=list(data[0])
  for row in data:row['verdict']='CORRECT';row['reviewer']='Synthetic human fixture'
  with out.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(data)
  human_audit_import(e.con,e.cfg,out,'Synthetic human fixture')
  g=checks(e.con,e.cfg);self.assertFalse([x for x in g if x['status']!='PASS'],g)
  result=export_all(e.con,e.cfg,e.root/'exports/ready')
  self.assertEqual(result['status'],'READY_TO_USE',result)
  manifest=json.loads((e.root/'exports/ready/MANIFEST.json').read_text());self.assertTrue(manifest['ready_to_use'])
  for f in manifest['files']:self.assertEqual(sha256_file(e.root/'exports/ready'/f['file']),f['sha256'])
  final=sqlite3.connect(e.root/'exports/ready/TFM_DATABASE_CLASS_A_FINAL.sqlite')
  self.assertEqual(final.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],8)
  self.assertEqual(final.execute('SELECT COUNT(*) FROM raw_measurements').fetchone()[0],0)
  self.assertEqual(final.execute('PRAGMA integrity_check').fetchone()[0],'ok');final.close()
  book=load_workbook(e.root/'exports/ready/TFM_DATABASE_CLASS_A_FINAL.xlsx',read_only=True);self.assertIn('evidence_long',book.sheetnames);self.assertIn('raw_studies',book.sheetnames);book.close()
  import pandas as pd
  pq=pd.read_parquet(e.root/'exports/ready/A_direct_yield.parquet');self.assertEqual(len(pq),2)
 def test_partial_expected_slot_is_rejected(self):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');e.submit(t,e.triage(t));t=e.task('DESIGN','112');e.submit(t,e.design(t));t=e.task('EXTRACT_A','112');d=e.values(t);d['values']=d['values'][:2];d['slot_status'][0]['n_values']=2
  r=e.submit(t,d,'REJECTED');self.assertTrue(any('expected 4' in x for x in r['errors']),r)
 def test_pass_b_cannot_verify_docling_without_original_receipt(self):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');e.submit(t,e.triage(t));t=e.task('DESIGN','112');e.submit(t,e.design(t));t=e.task('EXTRACT_B','112');d=e.values(t)
  for v in d['values']:v.pop('receipt_id')
  r=e.submit(t,d,'REJECTED');self.assertTrue(any('receipt' in x for x in r['errors']),r)
 def test_foreign_source_id_is_rejected(self):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');e.submit(t,e.triage(t));t=e.task('DESIGN','112');e.submit(t,e.design(t));t=e.task('EXTRACT_A','112');d=e.values(t);d['values'][0]['source_file_id']='SOURCE_126'
  r=e.submit(t,d,'REJECTED');self.assertTrue(any('registered source' in x for x in r['errors']),r)
 def test_final_export_refuses_fail_even_without_validation_history(self):
  e=self.e;r=export_all(e.con,e.cfg,e.root/'exports/forbidden');self.assertEqual(r['status'],'BLOCKED');self.assertFalse((e.root/'exports/forbidden').exists())
 def test_changed_original_invalidates_source_view(self):
  e=self.e;(e.src/'112.pdf').write_bytes(b'changed')
  with self.assertRaises(ValueError):view(e.con,e.cfg,'SOURCE_112',page=1)
 def test_outside_scope_task_rejected(self):
  e=self.e
  with self.assertRaises(ValueError):
   with tx(e.con):create_task(e.con,e.cfg,'1112','TRIAGE')
 def test_baseline_import_idempotent_and_different_input_blocked(self):
  e=self.e;sha=sha256_file(e.wb);self.assertEqual(import_workbook(e.con,e.wb)['studies'],2);self.assertEqual(sha,sha256_file(e.wb));other=e.data/'other.xlsx';shutil.copy2(e.wb,other);w=load_workbook(other);w['studies']['C2']='changed';w.save(other)
  with self.assertRaises(ValueError):import_workbook(e.con,other)
 def test_patch_is_applied_and_input_workbook_unchanged(self):
  e=self.e;sha=sha256_file(e.wb);e.prepare(patch=True)
  t=e.task('PATCH_REVIEW','112');pid=rows(e.con,"SELECT patch_id FROM wf_core_patches WHERE status='PROPOSED'")[0]['patch_id']
  e.submit(t,{**e.hdr(t),'decisions':[{'patch_id':pid,'decision':'ACCEPT','receipt_id':e.receipts['SOURCE_112'],'source_file_id':'SOURCE_112','reason':'original Methods p1'}]})
  self.assertEqual(e.con.execute("SELECT stress_level FROM arms WHERE arm_id='112_S'").fetchone()[0],'100 mM');self.assertEqual(sha256_file(e.wb),sha)
 def test_root_and_unknown_yield_attributes_excluded_from_strict_marts(self):
  e=self.e;e.prepare();e.con.execute("UPDATE an_target_values SET endpoint='DRY_BIOMASS',organ_scope='ROOT'");build(e.con,e.cfg)
  self.assertEqual(len(build_frames(e.con,e.cfg)['A_direct_dry_biomass']),0)
  e.con.execute("UPDATE an_target_values SET endpoint='FRUIT_YIELD',yield_scope='UNSPECIFIED'");build(e.con,e.cfg)
  self.assertEqual(len(build_frames(e.con,e.cfg)['A_direct_yield']),0)
 def test_missing_uncertainty_blocks_weighted_meta_but_keeps_verified_ml_targets(self):
  e=self.e;e.prepare();e.con.execute('UPDATE an_target_values SET sd=NULL,sd_norm=NULL');build(e.con,e.cfg);f=build_frames(e.con,e.cfg)
  self.assertEqual(len(f['A_direct_yield']),2);self.assertEqual(len(f['A_meta_yield_weighted']),0);self.assertGreater(len(f['A_descriptive']),0);self.assertTrue((f['evidence_long']['weighted_eligible']==0).all())
 def test_confirmed_preprint_filters_marts_and_links_cluster(self):
  e=self.e;e.prepare();e.con.execute("INSERT INTO wf_relations(study_a,study_b,relation,status) VALUES('112','126','PREPRINT_OF','CONFIRMED')");build(e.con,e.cfg);f=build_frames(e.con,e.cfg)
  self.assertEqual(set(f['evidence_long']['study_id']),{'126'});self.assertEqual(dependency_clusters(e.con)['112'],dependency_clusters(e.con)['126'])
 def test_stale_human_audit_cannot_be_imported(self):
  e=self.e;e.prepare();out=e.root/'work/audit.csv';human_audit_export(e.con,e.cfg,out);e.con.execute('UPDATE an_target_values SET mean=mean+1')
  with self.assertRaisesRegex(ValueError,'changed'):human_audit_import(e.con,e.cfg,out,'Human reviewer')
 def test_blind_pass_b_packet_drops_prior_values_and_results(self):
  from tfmlib.context import build_packet
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');e.submit(t,e.triage(t));t=e.task('DESIGN','112');e.submit(t,e.design(t));t=e.task('EXTRACT_B','112');p=build_packet(e.con,e.cfg,t);d=json.loads(p.read_text());self.assertNotIn('target_measurements',d['study']);self.assertNotIn('triage',d['study'])
 def test_unknown_allocation_cannot_supply_weighted_variance(self):
  e=self.e;e.prepare();e.con.execute("UPDATE wf_design_experiments SET allocation='REPEATED'");build(e.con,e.cfg)
  self.assertTrue(all(r['var_effect'] is None for r in rows(e.con,'SELECT * FROM an_contrasts')))

 def test_source_supported_inventory_correction_needs_both_passes(self):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');d=e.triage(t);d['slots'][0]['expected_n_values']=5;e.submit(t,d);t=e.task('DESIGN','112');e.submit(t,e.design(t))
  for tt in ('EXTRACT_A','EXTRACT_B'):
   t=e.task(tt,'112');d=e.values(t);sid=d['slot_status'][0]['slot_id'];d['inventory_corrections']=[{'slot_id':sid,'expected_n_values':4,'source_file_id':'SOURCE_112','receipt_id':e.receipts['SOURCE_112'],'reason':'Original table has exactly C S B SB, four cells; initial count five was wrong'}];e.submit(t,d)
   actual=e.con.execute('SELECT expected_n_values FROM wf_target_slots WHERE slot_id=?',(sid,)).fetchone()[0];self.assertEqual(actual,5 if tt=='EXTRACT_A' else 4)
  self.assertEqual(e.con.execute('SELECT status FROM wf_target_slots WHERE slot_id=?',(sid,)).fetchone()[0],'VERIFIED')
 def test_repeated_identical_submission_is_idempotent(self):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');d=e.triage(t);e.submit(t,d);before=e.con.execute('SELECT COUNT(*) FROM wf_target_slots').fetchone()[0];r=e.submit(t,d);self.assertTrue(r['idempotent_replay']);self.assertEqual(e.con.execute('SELECT COUNT(*) FROM wf_target_slots').fetchone()[0],before)
 def test_true_AxB_factorial_known_effect_and_variance(self):
  e=self.e;e.prepare();mapping={'E1.C':('S1','NONE','[]',0),'E1.S':('S1','A','["A@dose1"]',1),'E1.B':('S1','B','["B@dose1"]',1),'E1.SB':('S1','AB','["A@dose1","B@dose1"]',2)}
  for arm,(stress,bio,comps,n) in mapping.items():e.con.execute('UPDATE wf_design_arms SET stress_code=?,bio_code=?,component_codes=?,n_bio_components=? WHERE arm_key=?',(stress,bio,comps,n,arm));e.con.execute('UPDATE an_target_values SET stress_code=?,bio_code=? WHERE arm_key=?',(stress,bio,arm))
  build(e.con,e.cfg);cs=rows(e.con,"SELECT * FROM an_contrasts WHERE contrast_type='AxB'");self.assertEqual(len(cs),2)
  expected=math.log(1.2*1.1/(1.*1.3));var=sum(.1**2/(4*m*m) for m in (1.2,1.1,1.,1.3))
  for c in cs:self.assertAlmostEqual(c['effect'],expected,12);self.assertAlmostEqual(c['var_effect'],var,12)
 def test_shared_control_covariance_is_computed(self):
  e=self.e;e.prepare();cs={c['contrast_type']:c for c in rows(e.con,"SELECT * FROM an_contrasts WHERE study_id='112'")};a,b=cs['SB_vs_S']['contrast_id'],cs['SxB']['contrast_id'];r=e.con.execute('SELECT covariance FROM an_covariance WHERE (contrast_a=? AND contrast_b=?) OR (contrast_a=? AND contrast_b=?)',(a,b,b,a)).fetchone()
  self.assertAlmostEqual(r[0],.1**2/(4*1.2**2)+.1**2/(4*1.**2),12)
 def test_figure_two_independent_vector_readings_promote_known_truth(self):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');d=e.triage(t);d['slots'][0].update(source_kind='FIGURE',figure_item_id='112::FIG_001',locator_label='Figure 1');e.submit(t,d);t=e.task('DESIGN','112');e.submit(t,e.design(t));sid=rows(e.con,'SELECT slot_id FROM wf_target_slots')[0]['slot_id']
  for tt,pa in [('FIGURE_A','FA'),('FIGURE_B','FB')]:
   t=e.task(tt,'112');panel={'figure_item_id':'112::FIG_001','slot_id':sid,'source_file_id':'SOURCE_112','page':1,'figure_label':'Figure 1','panel':'single','image_path':str(e.src/'112.pdf'),'coord_space':'pdf_pt','value_axis':'y','endpoint':'FRUIT_YIELD','yield_scope':'TOTAL','mass_basis':'FRESH','denominator':'PER_PLANT','harvest_window':'CUMULATIVE','unit_raw':'kg/plant','axis':{'scale':'linear','ticks':[{'px':400-100*v,'value':v,'label_text':str(v)} for v in (0,1,2)]},'error_bar_type':'SD','n':4,'n_unit':'plots','n_source':'p1 legend','points':[{'arm_key':'E1.'+arm,'timepoint_key':'H_TOT','px_mean':400-100*m,'px_err_hi':390-100*m,'px_err_lo':None,'error_bar_status':'DIGITIZED_UPPER_ONLY','coordinate_uncertainty':.05,'error_bar_relative_uncertainty':.01} for arm,m in [('C',1.1),('S',1.),('B',1.3),('SB',1.2)]],'verbatim_caption':'Original synthetic Figure 1, mean plus SD, n=4 independent plots.','confidence':'HIGH','receipt_id':e.receipts['SOURCE_112'],'relative_uncertainty':.01,'source_cell':'Figure 1 bars C S B SB, total cumulative yield','probe_used':'vector_probe'}
   e.submit(t,{**e.hdr(t),'pass':pa,'panels':[panel],'slot_status':[{'slot_id':sid,'status':'EXTRACTED','n_values':4}]})
  v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0];self.assertAlmostEqual(v['mean'],1.2,12);self.assertAlmostEqual(v['sd'],.1,12)
 def test_bounded_raw_replicates_preserve_biological_unit(self):
  from tfmlib.derive import replicate_summary
  e=self.e;wb=Workbook();w=wb.active;w.title='Raw';w.append(['group','bio','value'])
  for row in [('G','P1',1),('G','P1',3),('G','P2',4),('G','P2',6)]:w.append(row)
  file=e.supp/'replicates.xlsx';wb.save(file)
  manifest=e.root/'manifests/source_manifest_A_462.csv'
  with manifest.open('a',newline='') as f:csv.writer(f).writerow(['112','SUPPLEMENT','RAW_112','replicates.xlsx'])
  index_sources(e.con,e.cfg)
  d={'source_file_id':'RAW_112','sheet':'Raw','range':'A1:C5','group_column':'group','group':'G','biological_id_column':'bio','value_column':'value','technical_repeats':True,'unit':'kg/plant','n_unit':'plots','endpoint':'FRUIT_YIELD','relevance':'primary target independent plot measurements'};req=e.root/'work/outbox/summary.json';req.parent.mkdir(parents=True,exist_ok=True);req.write_text(json.dumps(d));r=replicate_summary(e.con,e.cfg,req)['summary'];self.assertEqual(r['n'],2);self.assertEqual(r['mean'],3.5);self.assertAlmostEqual(r['sd'],math.sqrt(4.5),12)
  d['technical_repeats']=False;req.write_text(json.dumps(d))
  with self.assertRaises(ValueError):replicate_summary(e.con,e.cfg,req)
  d['endpoint']='TRANSCRIPTOMICS';req.write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,'omics'):replicate_summary(e.con,e.cfg,req)
 def test_human_incorrect_verdict_queues_autonomous_recheck(self):
  e=self.e;e.prepare();out=e.root/'work/audit.csv';human_audit_export(e.con,e.cfg,out)
  with out.open(encoding='utf-8-sig',newline='') as f:data=list(csv.DictReader(f));cols=list(data[0])
  for r in data:r['verdict']='CORRECT'
  data[0]['verdict']='INCORRECT';data[0]['notes']='Recheck source n in Methods'
  with out.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(data)
  human_audit_import(e.con,e.cfg,out,'Synthetic named human');self.assertGreater(e.con.execute("SELECT COUNT(*) FROM wf_tasks WHERE task_type='DESIGN' AND status='READY' AND scope_ref LIKE 'human-fix-%'").fetchone()[0],0)
 def test_post2023_data_is_quarantined_not_renamed_test(self):
  e=self.e;e.prepare();e.con.execute("UPDATE studies SET year=2024,temporal_eligibility='PROVISIONAL_YEAR_UNKNOWN' WHERE study_id='126'");f=build_frames(e.con,e.cfg);self.assertEqual(set(f['evidence_long']['study_id']),{'112'});self.assertEqual(e.con.execute("SELECT COUNT(*) FROM studies WHERE dataset_role LIKE '%TEST%'").fetchone()[0],0)

 def test_legacy_xls_original_view_and_replicate_summary(self):
  from tfmlib.derive import replicate_summary
  e=self.e;shutil.copy2(PKG/'tests/fixtures/legacy_source.xls',e.supp/'legacy_source.xls')
  with (e.root/'manifests/source_manifest_A_462.csv').open('a',newline='') as f:csv.writer(f).writerow(['112','SUPPLEMENT','LEGACY_XLS112','legacy_source.xls'])
  index_sources(e.con,e.cfg);r=view(e.con,e.cfg,'LEGACY_XLS112',sheet='Raw',cell_range='A1:C5');self.assertIn('original_view.txt',r['assets'][-1])
  req=e.root/'work/outbox/legacy_req.json';req.parent.mkdir(parents=True,exist_ok=True);req.write_text(json.dumps({'source_file_id':'LEGACY_XLS112','sheet':'Raw','range':'A1:C5','group_column':'group','group':'G','biological_id_column':'bio','value_column':'value','technical_repeats':True,'unit':'kg/plant','n_unit':'plots','endpoint':'FRUIT_YIELD','relevance':'primary yield raw plot data'}));self.assertEqual(replicate_summary(e.con,e.cfg,req)['summary']['mean'],3.5)
 def test_legacy_doc_converts_a_copy_without_modifying_original(self):
  e=self.e;p=e.supp/'legacy_supplement.doc';shutil.copy2(PKG/'tests/fixtures/legacy_supplement.doc',p)
  with (e.root/'manifests/source_manifest_A_462.csv').open('a',newline='') as f:csv.writer(f).writerow(['112','SUPPLEMENT','LEGACY_DOC112','legacy_supplement.doc'])
  index_sources(e.con,e.cfg);before=sha256_file(p);r=view(e.con,e.cfg,'LEGACY_DOC112',page=1);self.assertEqual(sha256_file(p),before);self.assertTrue(r['conversion']);self.assertTrue(any(x.endswith('.png') for x in r['assets']))
 def test_human_audit_xlsx_import_preserves_identifiers(self):
  e=self.e;e.prepare();out=e.root/'work/audit.csv';r=human_audit_export(e.con,e.cfg,out);book=load_workbook(r['xlsx']);ws=book['Human audit'];headers=[x.value for x in ws[1]]
  for row in range(2,ws.max_row+1):ws.cell(row,headers.index('verdict')+1,'CORRECT')
  book.save(r['xlsx']);book.close();result=human_audit_import(e.con,e.cfg,Path(r['xlsx']),'Synthetic named human');self.assertEqual(result['correct'],r['k'])
 def test_biotic_continuous_severity_MD_is_separate_from_yield(self):
  e=self.e;e.prepare();meta={'estimand_id':'BIOTIC_DISEASE_SEVERITY','effect_metric':'MD','scale_id':'percent_severity_same_scale','scale_type':'CONTINUOUS','scale_min':0,'scale_max':100,'assay':'visual continuous disease-area assessment','pathogen':'test pathogen','favorable_direction':'NEGATIVE'}
  for arm,mean,sd in [('E1.C',5,1),('E1.S',40,4),('E1.B',4,1),('E1.SB',30,3)]:e.con.execute("UPDATE an_target_values SET endpoint='BIOTIC_SEVERITY',context_key='SEVERITY1',outcome_context_json=?,mean=?,sd=?,mean_norm=NULL,sd_norm=NULL,unit_norm=NULL,unit_raw='percent severity' WHERE arm_key=?",(json.dumps(meta),mean,sd,arm))
  build(e.con,e.cfg);f=build_frames(e.con,e.cfg);self.assertEqual(len(f['A_direct_yield']),0);c=rows(e.con,"SELECT * FROM an_contrasts WHERE contrast_type='SB_vs_S'")[0];self.assertEqual(c['effect_metric'],'MD');self.assertEqual(c['effect'],-10);self.assertEqual(c['var_effect'],6.25);self.assertIsNone(c['pct_effect']);self.assertGreater(len(f['A_biotic_secondary']),0);self.assertEqual(len(f['A_productivity_components']),0)
 def test_biotic_binary_effect_and_no_pseudocount(self):
  e=self.e;e.prepare()
  for arm,events in [('E1.C',5),('E1.S',20),('E1.B',4),('E1.SB',10)]:
   meta={'estimand_id':'BIOTIC_DISEASE_INCIDENCE','effect_metric':'LOG_RR_BINARY','scale_id':'incidence_at_day14','scale_type':'BINARY','assay':'infected plants / independent assessed plants','pathogen':'test pathogen','favorable_direction':'NEGATIVE','events':events,'total':100,'binomial_independent':True};e.con.execute("UPDATE an_target_values SET endpoint='BIOTIC_INCIDENCE',context_key='INC14',outcome_context_json=?,mean=?,n=100,mean_norm=NULL,sd_norm=NULL,unit_norm=NULL,unit_raw='event count' WHERE arm_key=?",(json.dumps(meta),events,arm))
  build(e.con,e.cfg);c=rows(e.con,"SELECT * FROM an_contrasts WHERE contrast_type='SB_vs_S'")[0];self.assertAlmostEqual(c['effect'],math.log(.5));self.assertAlmostEqual(c['var_effect'],.13)
  for r in rows(e.con,"SELECT * FROM an_target_values WHERE arm_key='E1.SB'"):
   meta=json.loads(r['outcome_context_json']);meta['events']=0;e.con.execute('UPDATE an_target_values SET outcome_context_json=?,mean=0 WHERE tv_id=?',(json.dumps(meta),r['tv_id']))
  build(e.con,e.cfg);self.assertTrue(all(x['effect'] is None for x in rows(e.con,"SELECT * FROM an_contrasts WHERE contrast_type='SB_vs_S'")))
 def test_ordinal_biotic_values_are_preserved_without_forced_lnRR(self):
  e=self.e;e.prepare();meta={'estimand_id':'BIOTIC_ROOT_GALL','effect_metric':'DESCRIPTIVE_ORDINAL','scale_id':'gall_ordinal_0_5','scale_type':'ORDINAL','assay':'ordinal gall score','pathogen':'test nematode','favorable_direction':'NEGATIVE'}
  e.con.execute("UPDATE an_target_values SET endpoint='BIOTIC_ROOT_GALL',context_key='GALL',outcome_context_json=?",(json.dumps(meta),));build(e.con,e.cfg);f=build_frames(e.con,e.cfg);self.assertEqual(len(f['biotic_measurements_verified']),8);self.assertEqual(len(f['A_direct_yield']),0);self.assertTrue(all(x['effect'] is None for x in rows(e.con,'SELECT * FROM an_contrasts')))
 def test_posttreatment_context_never_becomes_primary_feature(self):
  e=self.e;e.prepare();e.con.execute("UPDATE wf_moderators SET availability='OBSERVED_POST_TREATMENT'");f=build_frames(e.con,e.cfg)['evidence_long'];self.assertNotIn('f_dose',f.columns);self.assertIn('context_dose',f.columns)
 def test_unverified_moderator_blocks_final_release(self):
  e=self.e;e.prepare();e.con.execute("UPDATE wf_moderators SET verification='UNVERIFIED'");g={r['gate']:r for r in checks(e.con,e.cfg)};self.assertEqual(g['used_moderators_independently_verified']['status'],'FAIL')
 def test_higher_priority_source_is_not_overwritten_by_lower_one(self):
  from tfmlib.reconcile import promote
  e=self.e;e.prepare();v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' LIMIT 1")[0];e.con.execute("UPDATE an_target_values SET source_kind='SUPP_DATASET' WHERE tv_id=?",(v['tv_id'],));v.update(mean=999,source_kind='TABLE');promote(e.con,e.cfg,'112',v['record_key'],v,'DOUBLE_AGREE',[]);self.assertNotEqual(e.con.execute('SELECT mean FROM an_target_values WHERE tv_id=?',(v['tv_id'],)).fetchone()[0],999)

 def test_table_figure_twin_metric_uses_normalized_units(self):
  from tfmlib.gates import accuracy
  e=self.e;e.prepare();v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0]
  e.con.execute("INSERT INTO wf_values(run_id,pass,study_id,record_key,arm_key,endpoint,timepoint_key,mean,mean_norm,unit_raw,unit_norm,source_kind) VALUES('TEST_TWIN','FA','112',?,'E1.SB','FRUIT_YIELD','H_TOT',1200,1.2,'g/plant','kg/plant','FIGURE')",(v['record_key'],));r=accuracy(e.con,e.cfg)['figure_twin_rel_error'];self.assertEqual(r['median'],0);self.assertEqual(r['p95'],0)

 def test_missing_interaction_variance_does_not_erase_the_verified_point_target(self):
  e=self.e;e.prepare();e.con.execute('UPDATE an_target_values SET sd=NULL,sd_norm=NULL');build(e.con,e.cfg);f=build_frames(e.con,e.cfg);self.assertEqual(len(f['A_strict_SxB']),2);self.assertEqual(len(f['A_meta_SxB_weighted']),0);self.assertTrue(f['A_strict_SxB']['var_effect'].isna().all())

class NumericTests(unittest.TestCase):
 def test_fig_dispersion_conflict_and_wide_axis_not_automatic_agreement(self):
  from tfmlib.reconcile import compare
  cfg=Config(PKG);base={'mean':10,'dispersion_type':'SE','dispersion_value':.1,'n':4,'unit_norm':'kg/plant','axis_range':100}
  self.assertIn('dispersion_value',compare(base,{**base,'dispersion_value':.9},cfg,True))
  self.assertIn('mean',compare({**base,'mean':1},{**base,'mean':3},cfg,True))
 def test_minimum_three_ticks(self):
  from tfmlib.figures import fit_axis,calibration_status
  cal=fit_axis([{'px':100,'value':0},{'px':0,'value':10}],'linear');self.assertEqual(calibration_status(cal,3,3,.015),'FAIL')
 def test_source_specified_CI_uses_correct_quantile(self):
  from tfmlib.stats import sd_from
  ci={'target':'ARM_MEAN','symmetric':True,'sidedness':'TWO_SIDED','level':.95,'distribution':'t','df':3}
  self.assertAlmostEqual(sd_from('CI95',.3182446305284263,4,ci),.2,10)
  ci['target']='ADJUSTED_MEAN';self.assertIsNone(sd_from('CI95',.3182446305284263,4,ci))
 def test_case_sensitive_mg_and_Mg_and_bare_g(self):
  from tfmlib.units import normalize
  self.assertEqual(normalize('Mg ha-1','FRUIT_YIELD')[0],'t/ha');self.assertIsNone(normalize('mg ha-1','FRUIT_YIELD')[0]);self.assertEqual(normalize('g','DRY_BIOMASS'),('g',1.,None))
 def test_MAD_zero_does_not_hide_outlier(self):
  from tfmlib.stats import mad_z
  self.assertTrue(math.isinf(mad_z([1,1,1,9])[-1]))
 def test_CI_without_distribution_never_becomes_SD(self):
  from tfmlib.stats import sd_from
  self.assertIsNone(sd_from('CI95',.2,4));self.assertAlmostEqual(sd_from('SE',.2,4),.4)
 def test_wrong_112_folder_never_matches_1112(self):
  from tfmlib.context import find_study_dir
  with tempfile.TemporaryDirectory(dir=PKG.parent) as d:
   root=Path(d);(root/'1112').mkdir();cfg=Config(PKG);cfg.paths={'docling_root':d,'docling_study_globs':['*{study_id}*']};self.assertIsNone(find_study_dir(cfg,'112'))
 def test_real_nested_Docling_and_versioned_handoff(self):
  from tfmlib.context import collect_sources
  with tempfile.TemporaryDirectory(dir=PKG.parent) as d:
   root=Path(d);p=root/'FULLTEXT__ID/parsed_v4_3';p.mkdir(parents=True);(p/'document.md').write_text('Text');(root/'STUDY_HANDOFF.v4_3.json').write_text('{}');r=collect_sources(Config(PKG),root);self.assertEqual(len(r['document_text']),1);self.assertEqual(len(r['handoff']),1)
 def test_all_json_schemas_valid(self):
  from jsonschema import Draft202012Validator
  for p in (PKG/'schema/json').glob('*.json'):Draft202012Validator.check_schema(json.loads(p.read_text()))
 def test_guard_rejects_bypass_and_human_forgery(self):
  hook=PKG/'.claude/hooks/guard_tool.py'
  for command,code in [('python tools/tfm.py status',0),('python tools/tfm.py human-audit-import x --reviewer author',2),('python tools/tfm.py close 112 --force',2),('python -c "import sqlite3"',2),('python tools/tfm.py status; rm x',2)]:
   p=subprocess.run([sys.executable,str(hook)],input=json.dumps({'tool_name':'Bash','tool_input':{'command':command}}),text=True,capture_output=True);self.assertEqual(p.returncode,code,(command,p.stderr))


class ErrorBarPolicyTests(unittest.TestCase):
 def setUp(self):
  from tfmlib.figures import fit_axis
  self.cal=fit_axis([{'px':400,'value':0},{'px':300,'value':1},{'px':200,'value':2}])
  self.panel={'error_bar_type':'UNCLEAR','coord_space':'pdf_pt','relative_uncertainty':.02}
  self.point={'px_mean':300.,'px_err_hi':290.,'px_err_lo':310.,'error_bar_status':'DIGITIZED_BOTH','coordinate_uncertainty':.05,'error_bar_relative_uncertainty':.02}
 def resolve(self):
  from tfmlib.figures import point_values
  from tfmlib.errorbars import resolve_error_bar
  m,e,i=point_values(self.point['px_mean'],self.point.get('px_err_hi'),self.point.get('px_err_lo'),self.cal)
  return resolve_error_bar(self.panel,self.point,self.cal,m,e,i,{'unlabelled_error_bars':'SE'})
 def test_unlabelled_real_bars_are_explicitly_assumed_se(self):
  r=self.resolve();self.assertEqual(r['dispersion_type'],'SE');self.assertEqual(r['dispersion_type_reported'],'UNCLEAR');self.assertEqual(r['dispersion_basis'],'USER_ASSUMED_SE');self.assertAlmostEqual(r['dispersion_value'],.1)
 def test_explicit_sd_is_preserved(self):
  self.panel['error_bar_type']='SD';r=self.resolve();self.assertEqual(r['dispersion_type'],'SD');self.assertEqual(r['dispersion_basis'],'SOURCE_REPORTED')
 def test_explicit_ci_is_never_defaulted_to_se(self):
  self.panel['error_bar_type']='CI95';self.assertEqual(self.resolve()['dispersion_type'],'CI95')
 def test_explicit_other_interval_is_not_assumed_se(self):
  self.panel['error_bar_type']='OTHER_INTERVAL';r=self.resolve();self.assertEqual(r['dispersion_type'],'UNCLEAR');self.assertEqual(r['dispersion_basis'],'OTHER_REPORTED_INTERVAL')
 def test_absent_bar_has_no_invented_se_or_zero(self):
  self.point.update(px_err_hi=None,px_err_lo=None,error_bar_status='ABSENT_IN_SOURCE',error_bar_note='No whisker is present in the original panel.')
  r=self.resolve();self.assertEqual(r['dispersion_type'],'NONE');self.assertIsNone(r['dispersion_value'])
 def test_visible_bar_cannot_be_omitted(self):
  self.point.update(px_err_hi=None,px_err_lo=None)
  with self.assertRaisesRegex(ValueError,'endpoint'):self.resolve()
 def test_unreadable_bar_requires_original_recovery_attempts(self):
  self.point.update(px_err_hi=None,px_err_lo=None,error_bar_status='NOT_READABLE',error_bar_note='Original panel inspected but cap is merged with annotation.',recovery_attempts=1)
  with self.assertRaisesRegex(ValueError,'retry'):self.resolve()
  self.point['recovery_attempts']=2;r=self.resolve();self.assertEqual(r['dispersion_basis'],'NOT_READABLE');self.assertIsNone(r['dispersion_value'])
 def test_short_bar_with_over_5pct_resolution_is_rejected(self):
  self.point.update(coordinate_uncertainty=1.,error_bar_relative_uncertainty=.05)
  with self.assertRaises(ValueError):self.resolve()
 def test_declared_bound_cannot_understate_geometry(self):
  self.point['error_bar_relative_uncertainty']=.001
  with self.assertRaisesRegex(ValueError,'understates'):self.resolve()
 def test_asymmetric_value_bounds_are_retained_without_forced_se(self):
  self.point['px_err_lo']=320.;r=self.resolve();self.assertEqual(r['dispersion_basis'],'ASYMMETRIC_INTERVAL');self.assertIsNone(r['dispersion_value']);self.assertAlmostEqual(json.loads(r['error_bar_bounds_json'])['lower'],.8)
 def test_log_axis_asymmetry_checked_in_source_value_space(self):
  from tfmlib.figures import fit_axis,point_values
  cal=fit_axis([{'px':300,'value':1},{'px':200,'value':10},{'px':100,'value':100}],'log10')
  mean,error,info=point_values(200,190,210,cal);self.assertGreater(info['asymmetry'],.1)
 def test_raster_precision_cannot_claim_subpixel_certainty(self):
  self.panel['coord_space']='image_px'
  with self.assertRaisesRegex(ValueError,'half a pixel'):self.resolve()

class ErrorBarIntegrationTests(unittest.TestCase):
 def setUp(self):self.e=Env()
 def tearDown(self):self.e.close()
 def figure(self,n=4,reported='UNCLEAR',bad_b=False):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');d=e.triage(t);d['slots'][0].update(source_kind='FIGURE',figure_item_id='112::FIG_001',locator_label='Figure 1');e.submit(t,d);t=e.task('DESIGN','112');e.submit(t,e.design(t));sid=rows(e.con,'SELECT slot_id FROM wf_target_slots')[0]['slot_id']
  for tt,pa in [('FIGURE_A','FA'),('FIGURE_B','FB')]:
   t=e.task(tt,'112');panel={'figure_item_id':'112::FIG_001','slot_id':sid,'source_file_id':'SOURCE_112','page':1,'figure_label':'Figure 1','panel':'single','image_path':str(e.src/'112.pdf'),'coord_space':'pdf_pt','value_axis':'y','endpoint':'FRUIT_YIELD','yield_scope':'TOTAL','mass_basis':'FRESH','denominator':'PER_PLANT','harvest_window':'CUMULATIVE','unit_raw':'kg/plant','axis':{'scale':'linear','ticks':[{'px':400-100*v,'value':v,'label_text':str(v)} for v in (0,1,2)]},'error_bar_type':reported,'n':n,'n_unit':'plots' if n else None,'n_source':'original independent plot description' if n else None,'points':[{'arm_key':'E1.'+arm,'timepoint_key':'H_TOT','px_mean':400-100*m,'px_err_hi':390-100*m,'px_err_lo':None,'error_bar_status':'DIGITIZED_UPPER_ONLY','coordinate_uncertainty':.05,'error_bar_relative_uncertainty':.02} for arm,m in [('C',1.1),('S',1.),('B',1.3),('SB',1.2)]],'verbatim_caption':'Synthetic original graphic; visible upper whiskers, original type not stated.','confidence':'HIGH','receipt_id':e.receipts['SOURCE_112'],'relative_uncertainty':.02,'source_cell':'Figure 1 bars C S B SB; cumulative yield','probe_used':'vector_probe'}
   if bad_b and pa=='FB':panel['points'][-1].update(px_mean=220.,px_err_hi=210.)
   e.submit(t,{**e.hdr(t),'pass':pa,'panels':[panel],'slot_status':[{'slot_id':sid,'status':'EXTRACTED','n_values':4}]})
  build(e.con,e.cfg)
 def test_assumed_se_persists_through_sd_contrasts_and_export(self):
  self.figure();e=self.e;v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0]
  self.assertEqual(v['dispersion_type_reported'],'UNCLEAR');self.assertEqual(v['dispersion_type'],'SE');self.assertAlmostEqual(v['sd'],.2)
  r=build_frames(e.con,e.cfg)['A_direct_yield'].iloc[0];self.assertEqual(r['uncertainty_assumed'],1);self.assertEqual(r['weighted_eligible'],1);self.assertEqual(r['weighted_reported_uncertainty_only_eligible'],0);self.assertIn('USER_ASSUMED_SE',r['flags'])
 def test_no_n_keeps_se_and_ml_point_without_invented_sd(self):
  self.figure(n=None);e=self.e;v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0];self.assertAlmostEqual(v['dispersion_value'],.1);self.assertIsNone(v['sd']);frames=build_frames(e.con,e.cfg);self.assertEqual(len(frames['A_direct_yield']),1);self.assertEqual(len(frames['A_meta_yield_weighted']),0)
 def test_table_mean_can_gain_graphical_uncertainty_with_separate_provenance(self):
  from tfmlib.reconcile import promote
  e=self.e;e.prepare();v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0];e.con.execute("UPDATE an_target_values SET dispersion_value=NULL,dispersion_type='NONE',sd=NULL,sd_norm=NULL,dispersion_provenance_json=NULL WHERE tv_id=?",(v['tv_id'],))
  fig={**v,'mean':1.21,'source_kind':'FIGURE','dispersion_type':'SE','dispersion_value':.1,'dispersion_type_reported':'UNCLEAR','dispersion_basis':'USER_ASSUMED_SE','locator':'Figure 1 bar SB','dispersion_provenance_json':None}
  promote(e.con,e.cfg,'112',v['record_key'],fig,'DOUBLE_AGREE',json.loads(v['basis_value_ids']))
  out=rows(e.con,'SELECT * FROM an_target_values WHERE tv_id=?',(v['tv_id'],))[0];self.assertEqual(out['mean'],1.2);self.assertEqual(out['source_kind'],'TABLE');self.assertAlmostEqual(out['sd'],.2);self.assertEqual(json.loads(out['dispersion_provenance_json'])['source_kind'],'FIGURE')
 def test_incompatible_uncertainty_goes_to_agent_adjudicator(self):
  from tfmlib.reconcile import promote
  e=self.e;e.prepare();v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0];e.con.execute("UPDATE an_target_values SET dispersion_value=NULL,sd=NULL,sd_norm=NULL WHERE tv_id=?",(v['tv_id'],));fig={**v,'mean':1.263,'source_kind':'FIGURE','dispersion_value':.1,'dispersion_provenance_json':None}
  promote(e.con,e.cfg,'112',v['record_key'],fig,'DOUBLE_AGREE',json.loads(v['basis_value_ids']));self.assertEqual(rows(e.con,"SELECT * FROM wf_reconciliation WHERE family='SOURCE_COMPLEMENT'")[0]['status'],'OPEN');self.assertTrue(rows(e.con,"SELECT * FROM wf_tasks WHERE task_type='ADJUDICATE' AND status='READY'"))
 def test_later_exact_mean_keeps_earlier_graphical_se_with_unit_conversion(self):
  from tfmlib.reconcile import promote
  self.figure();e=self.e;v=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0]
  table={**v,'mean':1200.,'unit_raw':'g/plant','source_kind':'TABLE','locator':'Table 1 exact mean SB','dispersion_type':'NONE','dispersion_value':None,'dispersion_provenance_json':None}
  promote(e.con,e.cfg,'112',v['record_key'],table,'DOUBLE_AGREE',json.loads(v['basis_value_ids']))
  out=rows(e.con,'SELECT * FROM an_target_values WHERE tv_id=?',(v['tv_id'],))[0];self.assertEqual(out['mean'],1200);self.assertEqual(out['source_kind'],'TABLE');self.assertAlmostEqual(out['dispersion_value'],100);self.assertAlmostEqual(out['sd'],200);self.assertEqual(json.loads(out['dispersion_provenance_json'])['unit_raw'],'kg/plant')
 def test_adjudicator_can_requeue_independent_figure_readings_without_human(self):
  self.figure(bad_b=True);e=self.e;t=e.task('ADJUDICATE','112');recs=rows(e.con,"SELECT * FROM wf_reconciliation WHERE study_id='112' AND status='OPEN'")
  decisions=[{'rec_id':r['rec_id'],'decision':'RECHECK_FIGURE','rationale':'Read the original vector caps again; no human digitization needed.','evidence_locator':'original Figure 1 p1','source_file_id':'SOURCE_112','receipt_id':e.receipts['SOURCE_112'],'source_cell':'Figure 1 SB bar and upper cap'} for r in recs]
  e.submit(t,{**e.hdr(t),'decisions':decisions})
  tasks=rows(e.con,"SELECT * FROM wf_tasks WHERE study_id='112' AND task_type IN ('FIGURE_A','FIGURE_B')")
  self.assertEqual(len(tasks),2);self.assertTrue(all(r['status']=='READY' and r['attempts']==0 for r in tasks));self.assertFalse(rows(e.con,"SELECT * FROM wf_review WHERE status='OPEN'"));self.assertFalse(rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112'"))
  for kind in ('FIGURE_A','FIGURE_B'):
   task=e.task(kind,'112');payload=json.loads((e.root/'work/outbox'/f"{task['task_id']}.json").read_text());payload['panels'][0]['points'][-1].update(px_mean=280.,px_err_hi=270.);e.submit(task,payload)
  self.assertFalse(rows(e.con,"SELECT * FROM wf_reconciliation WHERE study_id='112' AND status='OPEN'"));value=rows(e.con,"SELECT * FROM an_target_values WHERE study_id='112' AND arm_key='E1.SB'")[0];self.assertAlmostEqual(value['mean'],1.2);self.assertAlmostEqual(value['sd'],.2)
 def test_higher_resolution_render_gets_distinct_receipt_and_preserves_old_image(self):
  from PIL import Image
  e=self.e;old=e.receipts['SOURCE_112'];old_payload=json.loads(rows(e.con,'SELECT payload FROM wf_source_receipts WHERE receipt_id=?',(old,))[0]['payload']);im=Path(next(x for x in old_payload['assets'] if x.endswith('.png')));old_hash=sha256_file(im)
  new=view(e.con,e.cfg,'SOURCE_112',page=1,dpi=360);self.assertNotEqual(old,new['receipt_id']);self.assertEqual(sha256_file(im),old_hash);newim=Path(next(x for x in new['assets'] if x.endswith('.png')))
  with Image.open(im) as a,Image.open(newim) as b:self.assertAlmostEqual(b.width/a.width,2,delta=.01)

class PrimaryRediscoveryTests(unittest.TestCase):
 def setUp(self):self.e=Env()
 def tearDown(self):self.e.close()
 def biomass_only(self,primary='ABSENT'):
  e=self.e;seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');d=e.triage(t)
  d['targets'].update(fruit_yield=primary,dry_biomass='PRESENT')
  d['slots'][0].update(endpoint='DRY_BIOMASS',description='Synthetic historical biomass-only inventory; primary harvest information missed')
  e.submit(t,d);return d
 def primary_gate(self):
  return next(g for g in checks(self.e.con,self.e.cfg) if g['gate']=='primary_target_absence_independently_reviewed')
 def second_biomass(self):
  e=self.e;t=e.task('TRIAGE_2ND','112');d=e.triage(t);d['pass']='P2';d['targets'].update(fruit_yield='ABSENT',dry_biomass='PRESENT');d['slots'][0].update(endpoint='DRY_BIOMASS',description='Independent original-source secondary-biomass inventory');return t,d
 def test_biomass_present_does_not_skip_independent_primary_search(self):
  self.biomass_only();e=self.e
  self.assertTrue(rows(e.con,"SELECT task_id FROM wf_tasks WHERE study_id='112' AND task_type='TRIAGE_2ND' AND status='READY'"))
  self.assertTrue(rows(e.con,"SELECT task_id FROM wf_tasks WHERE study_id='112' AND task_type='DESIGN' AND status='READY'"))
  self.assertEqual(self.primary_gate()['status'],'FAIL')
 def test_unclear_primary_is_researched_before_questioning_the_author(self):
  self.biomass_only('UNCLEAR');e=self.e
  self.assertFalse(rows(e.con,"SELECT * FROM wf_review WHERE study_id='112' AND kind='TRIAGE_UNCLEAR' AND status='OPEN'"))
  t,d=self.second_biomass();e.submit(t,d)
  self.assertEqual(rows(e.con,"SELECT yield_status FROM wf_study_status WHERE study_id='112'")[0]['yield_status'],'ABSENT')
 def test_secondary_availability_cannot_bypass_release_gate_by_cancelling_review(self):
  self.biomass_only();e=self.e;e.con.execute("UPDATE wf_study_status SET state='CLOSED' WHERE study_id='112'");e.con.execute("UPDATE wf_tasks SET status='CANCELLED' WHERE study_id='112' AND task_type='TRIAGE_2ND'")
  self.assertEqual(self.primary_gate()['status'],'FAIL')
  result=export_all(e.con,e.cfg,e.root/'exports/forbidden-primary');self.assertEqual(result['status'],'BLOCKED');self.assertFalse((e.root/'exports/forbidden-primary').exists())
 def test_second_search_recovers_primary_slot_and_preserves_secondary(self):
  self.biomass_only();e=self.e;t=e.task('DESIGN','112');e.submit(t,e.design(t))
  t=e.task('TRIAGE_2ND','112');d=e.triage(t);d['pass']='P2';e.submit(t,d)
  self.assertEqual({r['endpoint'] for r in rows(e.con,"SELECT endpoint FROM wf_target_slots WHERE study_id='112'")},{'FRUIT_YIELD','DRY_BIOMASS'})
  self.assertEqual(rows(e.con,"SELECT yield_status FROM wf_study_status WHERE study_id='112'")[0]['yield_status'],'PRESENT')
  self.assertTrue(rows(e.con,"SELECT * FROM wf_tasks WHERE study_id='112' AND task_type='DESIGN' AND scope_ref='triage-P2' AND status='READY'"))
 def test_independent_negative_search_requires_original_supplement_receipts(self):
  self.biomass_only();e=self.e;t,d=self.second_biomass();next(r for r in d['source_checks'] if r['source_file_id']=='SUPP_112')['receipt_ids']=[]
  r=e.submit(t,d,'REJECTED');self.assertTrue(any('original receipt required' in msg for msg in r['errors']),r)
 def test_second_search_packet_excludes_old_inventory_and_docling_answers(self):
  from tfmlib.context import build_packet
  self.biomass_only();e=self.e;folder=e.data/'docling/112';(folder/'tables').mkdir(parents=True)
  (folder/'document.md').write_text('# Results\nOLD_BIOMASS_ONLY_CONCLUSION')
  (folder/'tables/old.csv').write_text('OLD_TABLE_SENTINEL,123')
  t=e.task('TRIAGE_2ND','112');path=build_packet(e.con,e.cfg,t);packet=json.loads(path.read_text());context=(e.root/packet['context_md']).read_text()
  self.assertEqual(set(packet['study']),{'study_id','study','files'})
  for key in ('document_text','table_csv','handoff','inventory','evidence_index','figures_root'):self.assertNotIn(key,packet['sources'])
  self.assertNotIn('OLD_TABLE_SENTINEL',context);self.assertNotIn('OLD_BIOMASS_ONLY_CONCLUSION',context)
  self.assertEqual(packet['target_discovery']['primary'],'FRUIT_YIELD')
 def test_primary_negative_review_cannot_be_sampled_away_when_no_targets_found(self):
  e=self.e;e.cfg.pipeline['queue'].update(second_triage_fraction_no_target=0,second_triage_always_if_title_signal=False)
  seed_triage(e.con,e.cfg);t=e.task('TRIAGE','112');d=e.triage(t);d['targets'].update(fruit_yield='ABSENT');d['slots']=[];d['asset_inventory'][0].update(relevance='IRRELEVANT',disposition='NOT_ELIGIBLE',reason='Synthetic negative inventory routing fixture')
  e.submit(t,d);self.assertEqual(rows(e.con,"SELECT state FROM wf_study_status WHERE study_id='112'")[0]['state'],'NO_TARGET_PENDING');self.assertTrue(rows(e.con,"SELECT task_id FROM wf_tasks WHERE study_id='112' AND task_type='TRIAGE_2ND'"))
 def test_independent_primary_discovery_guard_blocks_prior_database_lookup(self):
  guard=self.e.root/'.claude/hooks/guard_blind.py'
  for command,allowed in [("python tools/tfm.py sql SELECT",False),("python tools/tfm.py study 112",False),("python tools/tfm.py source-view SOURCE_112 --page 1",True)]:
   proc=subprocess.run([sys.executable,str(guard)],input=json.dumps({'tool_name':'Bash','tool_input':{'command':command}}),capture_output=True,text=True)
   self.assertEqual(proc.returncode==0,allowed,(command,proc.stderr))
 def test_both_unresolved_primary_passes_create_one_scientific_question(self):
  self.biomass_only('UNCLEAR');e=self.e;t,d=self.second_biomass();d['targets']['fruit_yield']='UNCLEAR';e.submit(t,d)
  self.assertEqual(len(rows(e.con,"SELECT * FROM wf_review WHERE study_id='112' AND kind='TRIAGE_UNCLEAR' AND status='OPEN'")),1)
  self.assertEqual(self.primary_gate()['status'],'FAIL')

if __name__=='__main__':unittest.main(verbosity=2)
