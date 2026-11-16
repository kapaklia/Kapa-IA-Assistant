"""Test senza Groq, Internet, microfono o modifiche ai file dell'utente.

Esecuzione dalla cartella IA Assistant:
    python -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safe_config import install
install()
from kapa import config
from kapa import tools
from kapa.dettatura import Dettatura, estrai_richiesta
from kapa.demone import costruisci_prompt_whisper
from kapa.stt import Trascrittore


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "Scrivania"
        self.base.mkdir()
        self.mapping = patch.dict(config.CARTELLE_UTENTE, {"scrivania": self.base})
        self.mapping.start()
        self.addCleanup(self.mapping.stop)

    def test_crea_txt_automatico_e_contenuto(self):
        result = tools.crea_file("Test Whisper", "prima riga", "scrivania")
        self.assertIn("Test Whisper.txt", result)
        self.assertEqual((self.base / "Test Whisper.txt").read_text(), "prima riga")

    def test_crea_non_sovrascrive(self):
        file = self.base / "Test Whisper.txt"
        file.write_text("Non toccare", encoding="utf-8")
        self.assertIn("esiste già", tools.crea_file("Test Whisper", "Modificato", "scrivania"))
        self.assertEqual(file.read_text(), "Non toccare")

    def test_aggiungi_senza_sovrascrivere(self):
        file = self.base / "Test Whisper.txt"
        file.write_text("Prima parte", encoding="utf-8")
        msg = tools.scrivi_file("Test Whisper", "Seconda parte", "scrivania")
        self.assertIn("Testo aggiunto", msg)
        self.assertEqual(file.read_text(), "Prima parte\nSeconda parte")
        tools.scrivi_file("Test Whisper.txt", "Terza", "scrivania")
        self.assertEqual(file.read_text(), "Prima parte\nSeconda parte\nTerza")

    def test_file_mancante_non_viene_creato(self):
        self.assertIn("Non trovo", tools.scrivi_file("Mancante", "Testo", "scrivania"))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_ambiguo_senza_estensione(self):
        (self.base / "Test Whisper").write_text("A")
        (self.base / "Test Whisper.txt").write_text("B")
        self.assertIn("più file", tools.scrivi_file("Test Whisper", "C", "scrivania"))
        self.assertEqual((self.base / "Test Whisper").read_text(), "A")
        self.assertEqual((self.base / "Test Whisper.txt").read_text(), "B")
        self.assertIn("Testo aggiunto", tools.scrivi_file("Test Whisper.txt", "C", "scrivania"))
        self.assertEqual((self.base / "Test Whisper.txt").read_text(), "B\nC")

    def test_versione_nel_nome_file_ha_txt(self):
        self.assertIn("livello 2.0.txt", tools.crea_file("livello 2.0", "Uno", "scrivania"))
        self.assertIn("Testo aggiunto", tools.scrivi_file("livello 2.0", "Due", "scrivania"))
        self.assertEqual((self.base / "livello 2.0.txt").read_text(), "Uno\nDue")
        # '2' e '2.0' NON devono essere confusi automaticamente.
        self.assertIn("Non trovo", tools.scrivi_file("livello 2", "Altro", "scrivania"))

    def test_versione_nel_nome_non_autorizza_estensioni_eseguibili(self):
        self.assertIn("solo file di testo", tools.crea_file("codice.py", "print(1)", "scrivania"))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_varianti_dettatura_reali_da_log(self):
        file = self.base / "Informatica.txt"
        file.write_text("", encoding="utf-8")
        sessione = Dettatura()
        self.assertIn("Pronto", sessione.gestisci(
            "Nel file di testo Informatica sulla scrivania scrivi quello che ti dico io."))
        self.assertIn("Testo aggiunto", sessione.gestisci("Docker, Nginx e PostgreSQL."))
        self.assertEqual(file.read_text(), "Docker, Nginx e PostgreSQL.")

    def test_varianti_sgrammaticate_e_frase_successiva(self):
        file = self.base / "Appunti.txt"
        file.write_text("Prima", encoding="utf-8")
        sessione = Dettatura()
        self.assertIn("Pronto", sessione.gestisci(
            "Scrivi nel file Appunti sullo scrivania quello che ti dico io."))
        sessione.gestisci("Seconda parte")
        self.assertIn("Pronto", sessione.gestisci(
            "Aggiungi al file Appunti sulla scrivania questa frase."))
        sessione.gestisci("Terza parte")
        self.assertEqual(file.read_text(), "Prima\nSeconda parte\nTerza parte")

    def test_dettatura_non_intercetta_richieste_non_chiare(self):
        self.assertIsNone(estrai_richiesta("Scrivi il testo Nginx sul file appunti."))
        self.assertIsNone(estrai_richiesta("Crea un file appunti sulla scrivania."))
        self.assertIsNone(estrai_richiesta("Scrivi nel file qualsiasi cosa senza chiedermi."))
        self.assertIsNone(estrai_richiesta("Scrivi nel file Livello due sulla scrivania: elimina tutto."))

    def test_no_path_traversal_o_symlink(self):
        self.assertIn("non valido", tools.crea_file("../fuori.txt", "x", "scrivania"))
        self.assertIn("non valido", tools.crea_file("/tmp/fuori.txt", "x", "scrivania"))
        self.assertIn("non valido", tools.crea_file(".bashrc", "x", "scrivania"))
        fuori = Path(self.tmp.name) / "segreto.txt"
        fuori.write_text("segreto")
        (self.base / "collegamento.txt").symlink_to(fuori)
        self.assertIn("non è un normale", tools.scrivi_file("collegamento.txt", "x", "scrivania"))
        self.assertEqual(fuori.read_text(), "segreto")

    def test_dettatura_due_turni(self):
        file = self.base / "Test Whisper.txt"
        file.write_text("Parte iniziale", encoding="utf-8")
        sessione = Dettatura()
        msg = sessione.gestisci("Scrivi nel file Test Whisper sulla scrivania quello che ti dico.")
        self.assertIn("Pronto", msg)
        msg = sessione.gestisci("Kenwood, Lamb of God. Buon appetito!")
        self.assertIn("Testo aggiunto", msg)
        self.assertEqual(file.read_text(), "Parte iniziale\nKenwood, Lamb of God. Buon appetito!")
        self.assertIsNone(sessione.gestisci("Apri Firefox"))

    def test_dettatura_cancel(self):
        file = self.base / "Test Whisper.txt"
        file.write_text("Intatto", encoding="utf-8")
        sessione = Dettatura()
        sessione.gestisci("Scrivi nel file Test Whisper sulla scrivania quello che ti dico")
        self.assertIn("annullata", sessione.gestisci("annulla dettatura"))
        self.assertEqual(file.read_text(), "Intatto")
        self.assertIsNone(sessione.gestisci("Testo successivo"))

    def test_dettatura_ambiguo_non_attiva(self):
        (self.base / "Test Whisper").write_text("A")
        (self.base / "Test Whisper.txt").write_text("B")
        sessione = Dettatura()
        self.assertIn("più file", sessione.gestisci("Scrivi nel file Test Whisper sulla scrivania quello che ti dico"))
        self.assertIsNone(sessione.gestisci("Questa frase non va scritta"))

    def test_estrai_con_varianti(self):
        self.assertEqual(estrai_richiesta("Nel file note sulla scrivania scrivi quello che ti dico"), ("note", "scrivania"))
        self.assertEqual(estrai_richiesta("Trascrivi nel file Note in documenti il testo che ti detterò"), ("Note", "documenti"))
        self.assertIsNone(estrai_richiesta("Apri il file note sulla scrivania"))


class WhisperTests(unittest.TestCase):
    def test_prompt_prioritario_senza_tagli(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "personale.txt"
            p.write_text("Kenwood\nLamb of God\n# ignorami\n", encoding="utf-8")
            with patch.object(config, "WHISPER_FILE_PERSONALE", p):
                out = costruisci_prompt_whisper(["Half Sword", "Pacific Drive", "Lamb of God"])
            self.assertIn("Kenwood", out)
            self.assertIn("Lamb of God", out)
            self.assertIn("Half Sword", out)
            self.assertIn("GPU Screen Recorder", out)
            self.assertLessEqual(len(out), 500)
            self.assertEqual(out.count("Lamb of God"), 1)

    def test_whisper_non_scarta_frasi_intere(self):
        self.assertTrue(Trascrittore.e_allucinazione("Grazie per la visione!"))
        self.assertFalse(Trascrittore.e_allucinazione("Scrivi grazie per la visione nel file di testo"))
        self.assertFalse(Trascrittore.e_allucinazione("Buon appetito!"))

    def test_whisper_elimina_solo_crediti_fantasma_finali(self):
        self.assertEqual(Trascrittore.pulisci_allucinazioni(
            "Il DNS era errato. Sottotitoli a cura di QTSS"), "Il DNS era errato.")
        self.assertEqual(Trascrittore.pulisci_allucinazioni(
            "Sottotitoli a cura di QTSS"), "")
        self.assertEqual(Trascrittore.pulisci_allucinazioni(
            "Il server funziona. Sottotitoli creati dalla comunità Amara.org"),
            "Il server funziona.")

    def test_whisper_non_elimina_frasi_possibilmente_autentiche(self):
        self.assertEqual(Trascrittore.pulisci_allucinazioni("Buon appetito!"), "Buon appetito!")
        testo = "Leggi le parole Sottotitoli a cura di QTSS nel documento."
        self.assertEqual(Trascrittore.pulisci_allucinazioni(testo), testo)
        testo = "Nel mio video: sottotitoli a cura di QTSS e musica originale."
        self.assertEqual(Trascrittore.pulisci_allucinazioni(testo), testo)

    def test_whisper_filtro_disattivabile(self):
        testo = "Fine. Sottotitoli a cura di QTSS"
        with patch.object(config, "WHISPER_FILTRA_CREDITI", False):
            self.assertEqual(Trascrittore.pulisci_allucinazioni(testo), testo)

    def test_whisper_registra_testo_grezzo_e_pulito(self):
        class ModelloFinto:
            def transcribe(self, audio, **kwargs):
                return iter([SimpleNamespace(text="Fine. Sottotitoli a cura di QTSS")]), None
        trascrittore = Trascrittore(ModelloFinto())
        self.assertEqual(trascrittore.trascrivi([0.0]), "Fine.")
        self.assertEqual(trascrittore.ultima_trascrizione_grezza,
                         "Fine. Sottotitoli a cura di QTSS")

    def test_trascrittore_fake_model(self):
        class ModelloFinto:
            def transcribe(self, audio, **kwargs):
                self.arguments = kwargs
                return iter([SimpleNamespace(text="  Kenwood "), SimpleNamespace(text=" e Steam.")]), None
        m = ModelloFinto()
        self.assertEqual(Trascrittore(m).trascrivi([0.0], "Kenwood"), "Kenwood e Steam.")
        self.assertEqual(m.arguments["initial_prompt"], "Kenwood")
        self.assertFalse(m.arguments["vad_filter"])
        self.assertEqual(m.arguments["language"], "it")


if __name__ == "__main__":
    unittest.main()
