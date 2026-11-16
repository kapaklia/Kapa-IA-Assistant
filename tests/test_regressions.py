import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch, Mock

from safe_config import install
install()
from kapa import config
from kapa import tools
from kapa import main
from kapa import memoria
from kapa import root_tools
from kapa.screen_capture import select_monitor
from kapa.tool_validation import validate_arguments
from kapa.comandi_rapidi import riconosci, rifiuta_volume_non_valido


class MediaSelectionTests(unittest.TestCase):
    def runner(self, players, statuses=None):
        statuses = statuses or {}
        def run(command, **kwargs):
            if command == ['playerctl', '--list-all']:
                return NS(returncode=0, stdout='\n'.join(players))
            if command[-1] == 'status':
                name = command[1].split('=', 1)[1]
                status = statuses.get(name, 'Paused')
                return NS(returncode=1 if status == 'error' else 0, stdout=status)
            return NS(returncode=0, stdout='')
        return run

    def test_unique_playing_player_is_used_for_every_action(self):
        for action in tools.AZIONI_MULTIMEDIALI:
            with self.subTest(action=action), patch.object(tools.subprocess, 'run', side_effect=self.runner(
                    ['vlc', 'rhythmbox', 'spotify'], {'spotify': 'Playing'})) as run:
                result = tools.controllo_multimediale(action)
                command = tools.AZIONI_MULTIMEDIALI[action][0]
                self.assertEqual(run.call_args.args[0], ['playerctl', '--player=spotify', *command[1:]])
                self.assertIn('spotify', result)

    def test_multiple_players_are_selected_without_questions(self):
        for statuses, expected in (({'vlc': 'Playing', 'spotify': 'Playing'}, 'vlc'),
                                   ({}, 'vlc'), ({'vlc': 'error', 'spotify': 'Playing'}, 'spotify')):
            with self.subTest(statuses=statuses), patch.object(tools.subprocess, 'run', side_effect=self.runner(
                    ['vlc', 'spotify'], statuses)) as run:
                result = tools.controllo_multimediale('pausa')
                self.assertNotIn('specifica', result)
                self.assertEqual(run.call_args.args[0], ['playerctl', f'--player={expected}', 'pause'])

    def test_browser_priority_and_unresponsive_players(self):
        for players, states, expected in (
            (['spotify', 'brave.instance1'], {'brave.instance1': 'Playing'}, 'brave.instance1'),
            (['firefox', 'brave', 'vlc'], {'brave': 'Playing'}, 'brave'),
            (['spotify', 'brave'], {'spotify': 'Playing'}, 'brave'),
            (['broken', 'brave'], {'broken': 'error', 'brave': 'Playing'}, 'brave'),
            (['org.gnome.Epiphany', 'vlc'], {}, 'org.gnome.Epiphany'),
        ):
            with self.subTest(players=players), patch.object(tools.subprocess, 'run',
                    side_effect=self.runner(players, states)) as run:
                tools.controllo_multimediale('play')
                self.assertEqual(run.call_args.args[0], ['playerctl', f'--player={expected}', 'play'])

    def test_status_timeout_does_not_block_browser(self):
        runner = self.runner(['broken', 'brave'], {'brave': 'Playing'})
        def run(command, **kwargs):
            if command == ['playerctl', '--player=broken', 'status']:
                raise subprocess.TimeoutExpired(command, 1)
            return runner(command, **kwargs)
        with patch.object(tools.subprocess, 'run', side_effect=run) as mocked:
            tools.controllo_multimediale('pausa')
            self.assertEqual(mocked.call_args.args[0], ['playerctl', '--player=brave', 'pause'])

    def test_explicit_player_overrides_playing_player(self):
        with patch.object(tools.subprocess, 'run', side_effect=self.runner(
                ['vlc', 'spotify'], {'spotify': 'Playing'})) as run:
            result = tools.controllo_multimediale('pausa', lettore='VLC')
            self.assertIn('vlc', result)
            self.assertEqual(run.call_args.args[0], ['playerctl', '--player=vlc', 'pause'])
            self.assertEqual(run.call_count, 2)

    def test_single_paused_or_arbitrary_mpris_player_can_resume(self):
        for player in ('org.example.NewPlayer', 'vlc.instance123', 'firefox.instance45'):
            with self.subTest(player=player), patch.object(tools.subprocess, 'run', side_effect=self.runner([player])) as run:
                tools.controllo_multimediale('play')
                self.assertEqual(run.call_args.args[0], ['playerctl', f'--player={player}', 'play'])

    def test_names_instances_and_invalid_selectors(self):
        from kapa.lettori import scegli_lettore
        with patch.object(tools.subprocess, 'run', side_effect=self.runner(['vlc.instance1', 'vlc.instance2'])):
            self.assertEqual(scegli_lettore('vlc'), ('vlc.instance1', None))
            self.assertEqual(scegli_lettore('vlc.instance2'), ('vlc.instance2', None))
            for name in ('spotify', '%any', 'vlc,spotify', '*', '--all-players'):
                self.assertIsNone(scegli_lettore(name)[0])

    def test_unavailable_or_unresponsive_player_never_runs_action(self):
        with patch.object(tools.subprocess, 'run', side_effect=self.runner([])) as run:
            self.assertIn('Nessun lettore', tools.controllo_multimediale('play'))
            self.assertEqual(run.call_count, 1)
        with patch.object(tools.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertIn('non è installato', tools.controllo_multimediale('play'))
        with patch.object(tools.subprocess, 'run', side_effect=subprocess.TimeoutExpired('playerctl', 3)) as run:
            self.assertIn('tempo', tools.controllo_multimediale('play').lower())
            self.assertEqual(run.call_count, 1)

    def test_named_voice_commands_stay_local(self):
        for text, action, player in (
            ('metti in pausa Spotify', 'pausa', 'spotify'),
            ('metti play su Firefox', 'play', 'firefox'),
            ('prossima traccia su VLC', 'avanti', 'vlc'),
            ('ripeti la traccia in Rhythmbox', 'ripeti_traccia', 'rhythmbox'),
            ('pausa vlc.instance123', 'pausa', 'vlc.instance123'),
            ('prossima traccia di Spotify', 'avanti', 'spotify'),
        ):
            with self.subTest(text=text):
                parameters = {'azione': action, 'lettore': player}
                self.assertEqual(riconosci(text), ('controllo_multimediale', parameters))
                function = Mock(return_value='OK')
                with patch.object(main, 'chiamata_groq_sicura') as groq:
                    main.gestisci_richiesta(text, Mock(), tools_schema=[],
                                           funzioni={'controllo_multimediale': function})
                function.assert_called_once_with(**parameters)
                groq.assert_not_called()


class ReplayCommandTests(unittest.TestCase):
    def test_voice_cycle_records_correlated_activity(self):
        from kapa import demone, attivita
        diagnostic = {'percorso': 'locale', 'azioni': ['controllo_multimediale']}
        def handler(text):
            self.assertEqual(text, 'prossima traccia')
            return 'Traccia successiva.'
        handler.diagnostica = diagnostic
        recorder = Mock()
        recorder.registra.return_value = object()
        transcriber = Mock()
        transcriber.trascrivi.return_value = 'prossima traccia'
        transcriber.ultima_trascrizione_grezza = 'prossima traccia'
        transcriber.e_allucinazione.return_value = False
        worker = demone.Demone(handler, registratore=recorder, trascrittore=transcriber)
        with patch.object(demone, '_bip_pronto'), patch.object(demone, '_notifica'), \
             patch.object(demone, '_registra_trascrizione'), patch.object(demone, 'salva_audio'), \
             patch.object(demone, 'salva_trascrizione'), patch.object(attivita, 'registra_attivita') as record:
            worker._ciclo_vocale()
        event = record.call_args.args[0]
        self.assertEqual(event['sentito'], 'prossima traccia')
        self.assertEqual(event['esito'], 'Traccia successiva.')
        self.assertEqual(event['percorso'], 'locale')
        self.assertEqual(event['azioni'], ['controllo_multimediale'])
        self.assertEqual(worker._stato, 'attesa')

    def test_new_local_commands_and_diagnostics(self):
        cases = [
            ('prossima traccia', 'controllo_multimediale', {'azione': 'avanti'}),
            ('traccia precedente', 'controllo_multimediale', {'azione': 'indietro'}),
            ('ripeti la traccia', 'controllo_multimediale', {'azione': 'ripeti_traccia'}),
            ('ripeti la playlist', 'controllo_multimediale', {'azione': 'ripeti_playlist'}),
            ('disattiva ripetizione', 'controllo_multimediale', {'azione': 'disattiva_ripetizione'}),
            ('attiva riproduzione casuale', 'controllo_multimediale', {'azione': 'casuale'}),
            ('disattiva riproduzione casuale', 'controllo_multimediale', {'azione': 'disattiva_casuale'}),
            ('ricomincia il brano', 'controllo_multimediale', {'azione': 'ricomincia'}),
            ('apri Firefox', 'apri_applicazione', {'nome_app': 'firefox'}),
            ('apri il terminale', 'apri_applicazione', {'nome_app': 'konsole'}),
            ('leggi gli appunti', 'leggi_appunti', {}),
            ('registra lo schermo', 'avvia_registrazione_schermo', {}),
            ('ferma la registrazione', 'ferma_registrazione_schermo', {}),
            ('registra lo schermo per trenta secondi', 'registra_schermo_per', {'secondi': 30}),
            ('avvia buffer replay da sessanta secondi', 'avvia_buffer_replay', {'secondi': 60}),
        ]
        for text, name, arguments in cases:
            with self.subTest(text=text):
                action = Mock(return_value='Esito sintetico')
                diagnostic = {}
                with patch.object(main, 'chiamata_groq_sicura') as groq:
                    result = main.gestisci_richiesta(text, Mock(), tools_schema=[],
                                                    funzioni={name: action}, diagnostica=diagnostic)
                self.assertEqual(result, 'Esito sintetico')
                action.assert_called_once_with(**arguments)
                groq.assert_not_called()
                self.assertEqual(diagnostic, {'percorso': 'locale', 'azioni': [name]})

    def test_extra_details_negations_and_ambiguous_repeat_are_not_local(self):
        for text in ('ripeti', 'non aprire Firefox', 'apri Firefox e Steam',
                     'apri Firefox in modalità privata', 'non ripeti la traccia',
                     'prossima traccia e apri Spotify', 'registra lo schermo per zero secondi',
                     'avvia buffer replay da 601 secondi'):
            self.assertIsNone(riconosci(text), text)

    def test_multimedia_uses_correct_playerctl_commands(self):
        for action, arguments in (
            ('avanti', ['next']), ('indietro', ['previous']),
            ('ripeti_traccia', ['loop', 'Track']), ('ripeti_playlist', ['loop', 'Playlist']),
            ('disattiva_ripetizione', ['loop', 'None']), ('casuale', ['shuffle', 'On']),
            ('disattiva_casuale', ['shuffle', 'Off']), ('ricomincia', ['position', '0']),
        ):
            with self.subTest(action=action), patch('kapa.lettori.scegli_lettore', return_value=('vlc', None)), \
                 patch.object(tools.subprocess, 'run') as run:
                tools.controllo_multimediale(action)
                run.assert_called_once_with(['playerctl', '--player=vlc'] + arguments, check=True,
                                            capture_output=True, timeout=5)
        with patch('kapa.lettori.scegli_lettore', return_value=('vlc', None)), \
             patch.object(tools.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'playerctl')):
            self.assertIn('non supportata', tools.controllo_multimediale('ripeti_traccia'))

    def test_activity_log_roundtrip_and_partial_line(self):
        from kapa.attivita import registra_attivita, ultima_attivita
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'activity.jsonl'
            self.assertEqual(ultima_attivita(path), {})
            event = {'sentito': 'ripeti la traccia\nprova', 'esito': 'Ripetizione attivata.',
                     'percorso': 'locale', 'azioni': ['controllo_multimediale']}
            registra_attivita(event, path)
            with path.open('a') as stream:
                stream.write('{"incompleto":')
            self.assertEqual(ultima_attivita(path), event)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_explicit_replay_commands_work_without_groq(self):
        for text, function in (
            ('Avvia il buffer replay.', 'avvia_buffer_replay'),
            ('attiva buffer di replay', 'avvia_buffer_replay'),
            ('salva il replay', 'salva_replay'),
            ('salva i reblesi.', 'salva_replay'),
            ('salva il reblay', 'salva_replay'),
            ('ferma il buffer replay', 'ferma_buffer_replay'),
        ):
            with self.subTest(text=text):
                action = Mock(return_value='Eseguito')
                history = Mock()
                with patch.object(main, 'chiamata_groq_sicura') as groq:
                    result = main.gestisci_richiesta(
                        text, history, tools_schema=[], funzioni={function: action})
                self.assertEqual(result, 'Eseguito')
                action.assert_called_once_with()
                groq.assert_not_called()

    def test_ambiguous_or_complex_phrases_are_not_executed_locally(self):
        for text in ('son variabili', 'sol via rebli', 'non salva il replay',
                     'come salva il replay', 'salva il replay e apri Firefox',
                     'salva il replay di ieri', 'avvia replay per 60 secondi e apri Firefox',
                     'replay', 'salva il file'):
            with self.subTest(text=text):
                self.assertIsNone(riconosci(text))


class SecurityTests(unittest.TestCase):
    def test_gsr_uses_explicit_shareable_codecs_for_recording_and_replay(self):
        for extra in (['-o', '/tmp/test.mp4'],
                      ['-r', '30', '-c', 'mp4', '-o', '/tmp']):
            process = Mock()
            process.poll.return_value = None
            with patch.object(tools.subprocess, 'Popen', return_value=process) as launch:
                actual, error = tools._avvia_processo_gsr(extra, verifica_secondi=0)
            self.assertIs(actual, process)
            self.assertIsNone(error)
            command = launch.call_args.args[0]
            for flag, value in (('-k', 'h264'), ('-ac', 'aac'),
                                ('-pixfmt', 'yuv420'), ('-cr', 'limited')):
                self.assertEqual(command[command.index(flag) + 1], value)
            self.assertEqual(command[-len(extra):], extra)

    def test_optional_capture_filename_accepts_null_only_when_declared(self):
        for schema in (tools.SCHEMA_AVVIA_REGISTRAZIONE, tools.SCHEMA_FAI_SCREENSHOT):
            parameters = schema['function']['parameters']
            for arguments in ({}, {'nome_file': None}, {'nome_file': 'prova'}):
                self.assertEqual(validate_arguments(parameters, arguments), arguments)
            for value in (12, True, [], {}):
                with self.assertRaises(ValueError):
                    validate_arguments(parameters, {'nome_file': value})
        with self.assertRaises(ValueError):
            validate_arguments({'properties': {'nome_file': {'type': 'string'}}},
                               {'nome_file': None})

    def test_recording_null_filename_generates_mp4_without_real_capture(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(tools, '_processo_registrazione', None), \
             patch.object(tools, '_percorso_registrazione', None), \
             patch.object(tools, '_risolvi_cartella', return_value=Path(directory)), \
             patch.object(tools, '_avvia_processo_gsr', return_value=(NS(), None)) as launch:
            result = tools.avvia_registrazione_schermo(nome_file=None, backend='gsr')
            output = Path(launch.call_args.args[0][1])
            self.assertEqual(output.parent, Path(directory))
            self.assertTrue(output.name.startswith('registrazione_'))
            self.assertEqual(output.suffix, '.mp4')
            self.assertIn('Registrazione avviata', result)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.a, self.b = self.base / 'a', self.base / 'b'
        self.a.mkdir(); self.b.mkdir()
        p = patch.dict(config.CARTELLE_UTENTE, {'documenti': self.a, 'scrivania': self.b})
        p.start(); self.addCleanup(p.stop)

    def test_read_rejects_escape_and_symlink(self):
        secret = self.base / 'secret.txt'
        secret.write_text('SYNTHETIC')
        (self.a / 'link.txt').symlink_to(secret)
        for name in ('../secret.txt', str(secret), 'link.txt', '.env'):
            self.assertNotIn('SYNTHETIC', tools.leggi_file(name))

    def test_read_regular_file(self):
        (self.a / 'note.txt').write_text('Synthetic note')
        self.assertEqual(tools.leggi_file('note.txt'), 'Synthetic note')

    def test_folder_escape_rejected(self):
        for name in ('../outside', str(self.base / 'outside'), '.ssh'):
            tools.crea_cartella(name)
        self.assertFalse((self.base / 'outside').exists())

    def test_collision_preserves_both_files(self):
        (self.a / 'x.txt').write_text('source')
        (self.b / 'x.txt').write_text('destination')
        for operation in (tools.copia_file, tools.sposta_file):
            self.assertIn('esiste', operation('x.txt', 'documenti', 'scrivania'))
            self.assertEqual((self.a / 'x.txt').read_text(), 'source')
            self.assertEqual((self.b / 'x.txt').read_text(), 'destination')
        (self.a / 'other.txt').write_text('other')
        self.assertIn('esiste', tools.rinomina_file('x.txt', 'other.txt'))
        self.assertEqual((self.a / 'other.txt').read_text(), 'other')

    def test_move_and_rename(self):
        (self.a / 'x.txt').write_text('source')
        tools.sposta_file('x.txt', 'documenti', 'scrivania')
        self.assertFalse((self.a / 'x.txt').exists())
        self.assertEqual((self.b / 'x.txt').read_text(), 'source')
        tools.rinomina_file('x.txt', 'y.txt', 'scrivania')
        self.assertEqual((self.b / 'y.txt').read_text(), 'source')

    def test_video_path_rejected_without_launch(self):
        with patch.object(tools, '_avvia_processo_gsr') as launch:
            self.assertIn('non valido', tools.avvia_registrazione_schermo('../x'))
            launch.assert_not_called()

    def test_close_rejects_patterns(self):
        with patch.object(tools.subprocess, 'run') as run:
            for name in ('.*', '--help', '/tmp/script'):
                self.assertIn('non valido', tools.chiudi_applicazione(name))
            run.assert_not_called()

    def test_close_exact_and_checks_exit(self):
        with patch.object(tools.subprocess, 'run', return_value=NS(returncode=1)) as run:
            self.assertIn('Nessun processo', tools.chiudi_applicazione('firefox'))
            self.assertEqual(run.call_args.args[0], ['pkill','-i','-x','--','firefox'])

    def test_reminder_rejects_nonfinite(self):
        with patch.object(tools.threading, 'Timer') as timer:
            for n in (math.nan, math.inf, -1, 0, 1e20):
                self.assertIn('durata', tools.imposta_promemoria(n, 'synthetic'))
            timer.assert_not_called()

    def test_nobara_and_package_validation(self):
        self.assertEqual(root_tools.build_command('update', distro='nobara'), ['nobara-sync','cli'])
        for name in ('--help','gimp;id','a b','../x'):
            with self.assertRaises(ValueError):
                root_tools.build_command('install', name, 'fedora')

    def test_root_actions_are_limited_on_every_distro(self):
        expected = {
            'nobara': ['nobara-sync', 'cli'],
            'fedora': ['sudo', 'dnf', 'upgrade', '--refresh'],
            'debian': ['sudo', 'apt', 'update'],
            'arch': ['sudo', 'pacman', '-Syu'],
        }
        for distro, command in expected.items():
            self.assertEqual(root_tools.build_command('update', distro=distro), command)
            for action in ('remove', 'uninstall', 'shell', 'exec', 'reboot', ''):
                with self.assertRaises(ValueError):
                    root_tools.build_command(action, 'gimp', distro)
            for package in ('-x', '/tmp/a.rpm', 'x\ny', '$(id)', '`id`', 'x&&id', None):
                with self.assertRaises(ValueError):
                    root_tools.build_command('install', package, distro)
        self.assertNotIn('esegui_come_root', tools.FUNZIONI_DISPONIBILI)
        with patch.object(root_tools.subprocess, 'run') as run, \
                patch.object(root_tools.subprocess, 'Popen') as popen:
            self.assertIn('disabilitati', root_tools.esegui_come_root('id'))
            run.assert_not_called()
            popen.assert_not_called()

    def test_private_memory(self):
        with patch.object(memoria, 'CARTELLA_CONVERSAZIONI', self.base / 'history'):
            m = memoria.Memoria('test'); m.aggiungi({'role':'user','content':'synthetic'})
            m.salva_su_disco()
            saved = list((self.base / 'history').glob('*.json'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)

    def test_volume_result_clamped(self):
        with patch.object(tools.subprocess, 'run', return_value=NS(stdout='95% / 95%')), \
             patch.object(tools, 'imposta_volume', return_value='bounded') as set_volume:
            tools.regolazione_volume('alza', 20)
            set_volume.assert_called_once_with(100)

    def test_x11_clipboard(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(tools.subprocess, 'run', return_value=NS(stdout='synthetic')) as run:
            self.assertEqual(tools.leggi_appunti(), 'synthetic')
            self.assertEqual(run.call_args.args[0], ['xclip','-selection','clipboard','-o'])

    def test_empty_xdg_output_uses_fallback(self):
        with patch.object(config.subprocess, 'run', return_value=NS(stdout='')), patch.object(config.HOME.__class__, 'exists', return_value=False):
            result = config._rileva_cartella_utente('DOCUMENTS', 'Documenti', 'Documents')
        self.assertEqual(result, config.HOME / 'Documenti')


class GroqTests(unittest.TestCase):
    def response(self, calls=None, content=None):
        return NS(choices=[NS(message=NS(tool_calls=calls, content=content))])

    def test_final_receives_result(self):
        c = NS(id='call1', function=NS(name='leggi_file', arguments='{"nome_file":"x.txt"}'))
        replies = [self.response([c]), self.response(content='summary')]
        with patch.object(main, 'chiamata_groq_sicura', side_effect=replies) as api:
            main.gestisci_richiesta('leggi il file x.txt', memoria.Memoria('test'),
                                  funzioni={'leggi_file': lambda **_: 'SYNTHETIC RESULT'})
        final = api.call_args.kwargs['messages']
        self.assertEqual(final[-1]['role'], 'tool')
        self.assertIn('SYNTHETIC RESULT', final[-1]['content'])
        self.assertEqual(final[-2]['tool_calls'][0]['id'], 'call1')

    def test_timeout_after_action_keeps_result(self):
        c = NS(id='call1', function=NS(name='leggi_file', arguments='{"nome_file":"x.txt"}'))
        with patch.object(main, 'chiamata_groq_sicura', side_effect=[self.response([c]), TimeoutError()]):
            result = main.gestisci_richiesta('leggi il file', memoria.Memoria('test'),
                                            funzioni={'leggi_file': lambda **_: 'COMPLETED'})
        self.assertIn('COMPLETED', result)

    def test_unoffered_tool_never_runs(self):
        c = NS(id='bad', function=NS(name='aggiorna_sistema', arguments='{}'))
        with patch.object(main, 'chiamata_groq_sicura', return_value=self.response([c])), \
             patch.dict(main.FUNZIONI_DISPONIBILI, {'aggiorna_sistema': lambda: self.fail('executed')}):
            result = main.gestisci_richiesta('leggi il file', memoria.Memoria('test'), riassumi=False)
        self.assertIn('rifiutata', result)

    def test_bad_json_never_runs(self):
        for arguments in ('{bad', '[]', '{"nome_file":4}', '{"nome_file":"a", "extra":1}'):
            c = NS(id='bad', function=NS(name='leggi_file', arguments=arguments))
            with patch.object(main, 'chiamata_groq_sicura', return_value=self.response([c])):
                result = main.gestisci_richiesta('leggi il file', memoria.Memoria('test'),
                                               funzioni={'leggi_file': lambda **_: self.fail('executed')}, riassumi=False)
                self.assertIn('rifiutata', result)

    def test_current_text_not_truncated(self):
        m = memoria.Memoria('test')
        m.aggiungi({'role':'user','content':'x'*5000})
        self.assertEqual(len(main._messaggi_compatti(m)[-1]['content']), 5000)

    def test_volume_validation_finite(self):
        schema = {'properties': {'n': {'type':'number'}}, 'required':['n']}
        for n in (math.nan, math.inf, True, '1'):
            with self.assertRaises(ValueError): validate_arguments(schema, {'n':n})

    def test_rate_limit_does_not_retry(self):
        class FakeError(Exception):
            status_code = 429
            body = {}
            response = NS(headers={'retry-after':'3'})
        with patch.object(main, 'APIStatusError', FakeError), \
             patch.object(main.client.chat.completions, 'create', side_effect=FakeError()) as api:
            with self.assertRaises(main.LimiteGroq) as error:
                main.chiamata_groq_sicura(model='synthetic', messages=[])
            self.assertIn('4 secondi', str(error.exception))
            api.assert_called_once()

    def test_expired_deadline_never_calls_provider(self):
        with patch.object(main.client.chat.completions, 'create') as api:
            with self.assertRaises(TimeoutError):
                main.chiamata_groq_sicura(_scadenza=0, model='synthetic', messages=[])
            api.assert_not_called()

    def test_cancel_before_tool_execution(self):
        c = NS(id='call', function=NS(name='leggi_file', arguments='{"nome_file":"x"}'))
        cancelled = iter([False, True])
        with patch.object(main, 'chiamata_groq_sicura', return_value=self.response([c])):
            result = main.gestisci_richiesta('leggi il file', memoria.Memoria('test'),
                funzioni={'leggi_file':lambda **_: self.fail('executed')}, riassumi=False,
                annullato=lambda: next(cancelled))
        self.assertIn('annullata', result)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.monitors = [dict(name='virtual-left',primary=False,x=-1280,y=0,w=1280,h=720,scale=1),
                         dict(name='virtual-main',primary=True,x=0,y=0,w=1920,h=1080,scale=1)]

    def test_default_is_primary_not_first(self):
        self.assertEqual(select_monitor(self.monitors)['name'], 'virtual-main')

    def test_index_and_all(self):
        self.assertEqual(select_monitor(self.monitors, 'monitor', 1)['name'], 'virtual-left')
        self.assertEqual(select_monitor(self.monitors, 'monitor', 2)['name'], 'virtual-main')
        self.assertIsNone(select_monitor(self.monitors, 'tutti'))

    def test_invalid_index(self):
        for index in (0,3,True,'2'):
            with self.assertRaises(ValueError): select_monitor(self.monitors,'monitor',index)

    def test_active_window_excludes_grim(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY':'test'}), patch.object(tools.shutil,'which',return_value='/fake'):
            self.assertNotIn('grim', [n for n,_ in tools._comandi_screenshot(Path('/fake/capture'), 'finestra')])

    def test_gsr_timeout_retains_handle(self):
        fake = NS(poll=lambda: None, send_signal=lambda _: None,
                  wait=lambda **_: (_ for _ in ()).throw(subprocess.TimeoutExpired('fake', 10)))
        with patch.object(tools, '_processo_registrazione', fake):
            self.assertIn('chiusura', tools.ferma_registrazione_schermo())
            self.assertIs(tools._processo_registrazione, fake)

    def test_local_screenshot_commands(self):
        self.assertEqual(riconosci('Fai uno screenshot'), ('fai_screenshot', {}))
        self.assertEqual(riconosci('Fai uno screenshot del monitor due'), ('fai_screenshot', {'destinazione':'monitor','monitor':2}))
        self.assertEqual(riconosci('Fai uno screenshot di tutti i monitor')[1], {'destinazione':'tutti'})
        self.assertEqual(riconosci('Fai uno screenshot della finestra attiva')[1], {'destinazione':'finestra'})

    def test_invalid_volume_numbers(self):
        for value in ('-5%', '2,5%', 'centouno per cento', 'duecentoventi per cento'):
            self.assertTrue(rifiuta_volume_non_valido('metti il volume al ' + value))

    def test_screenshot_crops_primary_with_negative_origin(self):
        try:
            from PySide6.QtGui import QImage, QColor
        except ImportError:
            self.skipTest('PySide6 non disponibile')
        screens = [dict(name='left',primary=False,x=-100,y=0,w=100,h=100,scale=1),
                   dict(name='main',primary=True,x=0,y=0,w=200,h=100,scale=1)]
        with tempfile.TemporaryDirectory() as directory:
            def capture(argv, **kwargs):
                image = QImage(300,100,QImage.Format.Format_RGB32)
                image.fill(QColor('red'))
                self.assertTrue(image.save(argv[-1], 'PNG'))
                return NS(returncode=0,stdout='',stderr='')
            with patch.dict(config.CARTELLE_UTENTE, {'immagini':Path(directory)}), \
                 patch('kapa.screen_capture.detect_monitors', return_value=screens), \
                 patch.object(tools,'_comandi_screenshot', side_effect=lambda p,*_: [('synthetic',['fake',str(p)])]), \
                 patch.object(tools.subprocess,'run',side_effect=capture):
                result = tools.fai_screenshot('test.png')
                self.assertIn('salvato', result)
                image = QImage(str(Path(directory) / 'test.png'))
                self.assertEqual((image.width(),image.height()), (200,100))
                self.assertIn('Esiste', tools.fai_screenshot('test.png'))

    def test_service_generator_quotes_spaces(self):
        from kapa.setup_assistant import service_text
        text = service_text(Path('/tmp/Synthetic project'), '/tmp/Synthetic venv/python')
        self.assertIn('ExecStart="/tmp/Synthetic venv/python" "/tmp/Synthetic project/main.py"', text)
        self.assertNotIn('sudo', text)


class VideoBackendTests(unittest.TestCase):
    def setUp(self):
        self.state = patch.multiple(tools, _registrazione_obs=None, _replay_obs=None,
                                    _processo_registrazione=None, _processo_buffer_replay=None)
        self.state.start()
        self.addCleanup(self.state.stop)

    def test_default_prefers_gsr_and_falls_back_only_when_missing(self):
        with patch.object(tools.shutil, 'which', return_value='/usr/bin/gpu-screen-recorder'):
            self.assertEqual(tools._backend_video('auto'), 'gsr')
            self.assertEqual(tools._backend_video('obs'), 'obs')
        with patch.object(tools.shutil, 'which', return_value=None):
            self.assertEqual(tools._backend_video('auto'), 'obs')
            self.assertEqual(tools._backend_video('gsr'), 'gsr')
        with self.assertRaises(ValueError):
            tools._backend_video('unknown')

    def test_obs_record_stop_remembers_backend_and_prevents_duplicate(self):
        session = Mock()
        session.call.side_effect = lambda name: ({'outputActive': False} if name == 'GetRecordStatus'
                                                else {'outputPath': '/tmp/video.mkv'} if name == 'StopRecord' else {})
        with patch.object(tools.obs_control, 'ObsSession', return_value=session), \
             patch.object(tools.shutil, 'which', return_value=None), \
             patch.object(tools, '_avvia_processo_gsr') as gsr:
            self.assertIn('Registrazione avviata con OBS', tools.avvia_registrazione_schermo())
            self.assertIn('già', tools.avvia_registrazione_schermo(backend='gsr'))
            session.call.side_effect = lambda name: {'outputActive': True} if name == 'GetRecordStatus' else {'outputPath': '/tmp/video.mkv'}
            self.assertIn('/tmp/video.mkv', tools.ferma_registrazione_schermo())
            session.call.assert_any_call('StopRecord')
            session.close.assert_called_once()
            gsr.assert_not_called()
            self.assertIsNone(tools._registrazione_obs)

    def test_refuses_to_take_over_manual_obs_capture(self):
        session = Mock()
        session.call.return_value = {'outputActive': True}
        with patch.object(tools.obs_control, 'ObsSession', return_value=session):
            self.assertIn('già', tools.avvia_registrazione_schermo(backend='obs'))
            session.call.assert_called_once_with('GetRecordStatus')
            session.close.assert_called_once()
            self.assertIsNone(tools._registrazione_obs)

    def test_obs_replay_uses_own_settings_and_routes_save_stop(self):
        session = Mock()
        session.call.return_value = {'outputActive': False}
        with patch.object(tools.obs_control, 'ObsSession', return_value=session) as connect:
            self.assertIn('durata', tools.avvia_buffer_replay(20, backend='obs'))
            connect.assert_not_called()
            self.assertIn('con OBS', tools.avvia_buffer_replay(backend='obs'))
            self.assertIn('richiesto', tools.salva_replay())
            session.call.assert_any_call('SaveReplayBuffer')
            session.call.return_value = {'outputActive': True}
            self.assertIn('fermato', tools.ferma_buffer_replay())
            session.call.assert_any_call('StopReplayBuffer')
            self.assertIsNone(tools._replay_obs)

    def test_gsr_failure_does_not_switch_to_obs(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(tools, '_risolvi_cartella', return_value=Path(directory)), \
             patch.object(tools.shutil, 'which', return_value='/usr/bin/gpu-screen-recorder'), \
             patch.object(tools, '_avvia_processo_gsr', return_value=(None, 'errore GSR')), \
             patch.object(tools.obs_control, 'ObsSession') as obs:
            self.assertEqual(tools.avvia_registrazione_schermo(), 'errore GSR')
            obs.assert_not_called()

    def test_explicit_backend_commands_and_negations(self):
        self.assertEqual(riconosci('registra lo schermo con OBS'),
                         ('avvia_registrazione_schermo', {'backend': 'obs'}))
        self.assertEqual(riconosci('fai un video di dieci secondi con OBS'),
                         ('registra_schermo_per', {'secondi': 10, 'backend': 'obs'}))
        self.assertEqual(riconosci('avvia il buffer replay con GPU Screen Recorder'),
                         ('avvia_buffer_replay', {'backend': 'gsr'}))
        self.assertIsNone(riconosci('non registra lo schermo con OBS'))

    def test_stop_error_keeps_session_and_cleanup_does_not_close_obs_app(self):
        session = Mock()
        session.call.side_effect = tools.obs_control.ObsError('connessione interrotta')
        with patch.object(tools, '_registrazione_obs', session):
            self.assertIn('interrotta', tools.ferma_registrazione_schermo())
            self.assertIs(tools._registrazione_obs, session)
            session.close.assert_not_called()
            session.call.side_effect = lambda name: {'outputActive': True} if name == 'GetRecordStatus' else {'outputPath': '/tmp/video.mkv'}
            tools.arresta_catture()
            session.call.assert_any_call('StopRecord')
            self.assertNotIn('Exit', [c.args[0] for c in session.call.call_args_list])

    def test_timer_cannot_stop_new_obs_recording(self):
        first, second = Mock(), Mock()
        first.call.return_value = {'outputActive': False}
        with patch.object(tools.obs_control, 'ObsSession', return_value=first), \
             patch.object(tools.threading, 'Timer') as timer, \
             patch.object(tools, 'ferma_registrazione_schermo') as stop:
            self.assertIn('10 secondi', tools.registra_schermo_per(10, backend='obs'))
            tools._registrazione_obs = second
            timer.call_args.args[1]()
            stop.assert_not_called()

    def test_obs_protocol_auth_and_correlated_response(self):
        import sys
        import hashlib
        import base64
        session_socket = Mock()
        sent = []
        session_socket.send.side_effect = lambda value: sent.append(json.loads(value))
        hello = {'op': 0, 'd': {'authentication': {'salt': 'salt', 'challenge': 'challenge'}}}
        def receive():
            if not sent:
                return json.dumps(hello)
            if sent[-1]['op'] == 1:
                return json.dumps({'op': 2, 'd': {}})
            return json.dumps({'op': 7, 'd': {'requestId': sent[-1]['d']['requestId'],
                                'requestStatus': {'result': True}, 'responseData': {'outputActive': False}}})
        session_socket.recv.side_effect = receive
        connect = Mock(return_value=session_socket)
        with patch.dict(sys.modules, {'websocket': NS(create_connection=connect)}), \
             patch.object(config, 'OBS_PASSWORD', 'test-only-password'):
            session = tools.obs_control.ObsSession()
            self.assertFalse(session.call('GetRecordStatus')['outputActive'])
            secret = base64.b64encode(hashlib.sha256(b'test-only-passwordsalt').digest())
            expected = base64.b64encode(hashlib.sha256(secret + b'challenge').digest()).decode()
            self.assertEqual(sent[0]['d']['authentication'], expected)
            self.assertNotIn('test-only-password', json.dumps(sent))
            self.assertEqual(sent[0]['d']['eventSubscriptions'], 0)
            session.close()
            session_socket.close.assert_called_once()
