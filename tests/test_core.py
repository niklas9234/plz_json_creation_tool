import json, sqlite3
from pathlib import Path
import pytest
from app.datenbank import Database
from app.datenbank.gebiete import ausgelieferte_gebietsdateien, lade_gebiete
from app.services import Verwaltung, BackupService
from app.modelle import UnternehmenEingabe
from app.geojson_export import GeoJSONExporter, dateiname_fuer_gewerk
from initial_import.importer import importiere

ROOT=Path(__file__).parents[1]
def database(tmp_path):
 db=Database(tmp_path/'test.db'); db.initialize(); lade_gebiete(db,ausgelieferte_gebietsdateien(ROOT)); return db

def test_datenbankverbindung_wird_nach_kontext_geschlossen(tmp_path):
 db=Database(tmp_path/'closed.db'); db.initialize()
 with db.connect() as con:
  assert con.execute('select 1').fetchone()[0] == 1
 with pytest.raises(sqlite3.ProgrammingError, match='closed'):
  con.execute('select 1')

def test_detailreiche_gebietsdateien_werden_geladen(tmp_path):
 db=database(tmp_path)
 with db.connect() as c:
  assert c.execute('select count(*) from gebiete').fetchone()[0] == 96
  deutschland=json.loads(c.execute("select geometrie from gebiete where schluessel='04'").fetchone()[0])
  luxemburg=json.loads(c.execute("select geometrie from gebiete where schluessel='LUX'").fetchone()[0])
  assert len(deutschland['coordinates'][0]) > 100
  assert deutschland['type'] == 'Polygon'
  assert luxemburg['type'] == 'MultiPolygon'

def test_verwaltung_und_gruppierter_export(tmp_path):
 db=database(tmp_path); v=Verwaltung(db)
 v.speichere_unternehmen(UnternehmenEingabe('Zulu GmbH','001',True,{'Gerüstbau':{'04','LUX'}}))
 v.speichere_unternehmen(UnternehmenEingabe('Alpha GmbH','002',True,{'Gerüstbau':{'04'}}))
 v.speichere_unternehmen(UnternehmenEingabe('Inaktiv','003',False,{'Gerüstbau':{'04'}}))
 with db.connect() as c: gid=c.execute("select id from gewerke where name='Gerüstbau'").fetchone()[0]
 path=GeoJSONExporter(db).exportieren(gid,tmp_path/'out'); doc=json.loads(path.read_text())
 assert path.name=='geruestbau.geojson'; assert len(doc['features'])==2
 feature=next(f for f in doc['features'] if f['properties']['gebiet']=='04')
 assert feature['properties']['firmen']==['Alpha GmbH','Zulu GmbH']; assert feature['properties']['anzahl_dienstleister']==2

def test_import_merge_duplicate_and_leading_zero(tmp_path):
 csv=tmp_path/'in.csv'; csv.write_text('Gewerk;Unternehmen;PPS_Nummer;PLZ\nKran;Firma;0007;04\nKran;Firma;0007;06\nKran;Firma;0007;06\n',encoding='utf8')
 report=importiere(csv,tmp_path/'import.db'); assert (report.unternehmen,report.zuordnungen,report.duplikate)==(1,2,1)
 with sqlite3.connect(tmp_path/'import.db') as c: assert c.execute('select pps_nummer from unternehmen').fetchone()[0]=='0007'

def test_import_rejects_conflict_atomically(tmp_path):
 csv=tmp_path/'in.csv'; csv.write_text('Gewerk;Unternehmen;PPS_Nummer;PLZ\nKran;A;1;04\nKran;B;1;06\n',encoding='utf8')
 report=importiere(csv,tmp_path/'import.db'); assert report.fehlerhafte_zeilen==1; assert not (tmp_path/'import.db').exists()

def test_import_trennt_firmen_mit_null_pps_und_ueberspringt_nicht_vergebene_plz2(tmp_path):
 csv=tmp_path/'in.csv'
 csv.write_text('Gewerk;Unternehmen;PPS_Nummer;PLZ\nKran;Ohne Nummer A;0;04\nKran;Ohne Nummer B;0;06\nKran;Firma;123;05\nKran;Firma;123;11\nKran;Firma;123;43\nKran;Firma;123;62\nKran;Firma;123;04\n',encoding='utf8')
 report=importiere(csv,tmp_path/'import.db')
 assert not report.fehler
 assert (report.unternehmen,report.zuordnungen,report.uebersprungene_zeilen)==(3,3,4)
 assert any('05' in hinweis and '11' in hinweis and '43' in hinweis and '62' in hinweis for hinweis in report.hinweise)
 with sqlite3.connect(tmp_path/'import.db') as c:
  assert c.execute('select name,pps_nummer from unternehmen order by name').fetchall()==[('Firma','123'),('Ohne Nummer A','0'),('Ohne Nummer B','0')]

def test_datenbank_erlaubt_mehrere_null_pps_ohne_echte_duplikate_zuzulassen(tmp_path):
 db=database(tmp_path)
 v=Verwaltung(db)
 v.speichere_unternehmen(UnternehmenEingabe('A','0',True,{'Kran':{'04'}}))
 v.speichere_unternehmen(UnternehmenEingabe('B','0',True,{'Kran':{'06'}}))
 v.speichere_unternehmen(UnternehmenEingabe('C','123',True,{'Kran':{'04'}}))
 with pytest.raises(ValueError, match='PPS-Nummer'):
  v.speichere_unternehmen(UnternehmenEingabe('D','123',True,{'Kran':{'06'}}))

def test_schema_version_eins_wird_fuer_null_pps_migriert(tmp_path):
 path=tmp_path/'alt.db'
 with sqlite3.connect(path) as con:
  con.executescript("""CREATE TABLE schema_version(version INTEGER NOT NULL); INSERT INTO schema_version VALUES (1);
   CREATE TABLE unternehmen(id INTEGER PRIMARY KEY,name TEXT NOT NULL,pps_nummer TEXT NOT NULL UNIQUE,aktiv INTEGER NOT NULL DEFAULT 1,erstellt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,geaendert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
   INSERT INTO unternehmen(name,pps_nummer) VALUES ('Bestehend','123');""")
 db=Database(path); db.initialize(); lade_gebiete(db,ausgelieferte_gebietsdateien(ROOT))
 with db.connect() as con:
  assert con.execute('select version from schema_version').fetchone()[0]==2
 Verwaltung(db).speichere_unternehmen(UnternehmenEingabe('Ohne Nummer A','0',True,{'Kran':{'04'}}))
 Verwaltung(db).speichere_unternehmen(UnternehmenEingabe('Ohne Nummer B','0',True,{'Kran':{'06'}}))

def test_backup_restore(tmp_path):
 db=database(tmp_path); backup=BackupService(db,tmp_path/'backups'); saved=backup.erstellen()
 with db.connect() as c: c.execute("insert into gewerke(name) values ('Test')")
 backup.wiederherstellen(saved)
 with db.connect() as c: assert c.execute("select count(*) from gewerke").fetchone()[0]==0

def test_filename(): assert dateiname_fuer_gewerk('Maler & Lackierer')=='maler-und-lackierer.geojson'
