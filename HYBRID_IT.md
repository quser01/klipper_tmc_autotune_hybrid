# klipper_tmc_autotune ibrido: chopper misurato, tutto il resto calcolato

[English version](HYBRID.md)

Questo fork di [klipper_tmc_autotune](https://github.com/andrewmcgr/klipper_tmc_autotune)
può usare i registri del chopper spreadCycle **misurati** sulla tua stampante da
[chopper-autotune](https://github.com/anton-vinogradov/chopper-autotune),
invece di quelli **calcolati** dal database dei motori. Tutto il resto lo
continua a regolare autotune, come nell'originale.

| Cosa | Chi lo decide |
|---|---|
| `tbl`, `toff`, `hstrt`, `hend`, `tpfd` | chopper-autotune (misura con l'accelerometro) |
| StealthChop / PWM (`pwm_grad`, `pwm_ofs`, `pwm_freq`) | autotune (modello del motore) |
| CoolStep, soglie StallGuard | autotune |
| `slope_control` del TMC2240, fullstep ad alta velocità | autotune |
| `run_current` | tu (`CHOPPER_CURRENT` di chopper-autotune può aiutare) |

> Stato: verificato con test automatici (`tests/test_hybrid.py`, 19 test, Klipper simulato).
> Non ancora provato su una stampante reale. Usalo a tuo rischio e tieni un backup della configurazione.

## Cosa cambia rispetto all'originale

1. Nuova opzione `measured_chopper: True` in `[autotune_tmc ...]`. Legge
   `driver_TBL`, `driver_TOFF`, `driver_HSTRT`, `driver_HEND` e `driver_TPFD`
   dalla sezione `[tmc... ...]` corrispondente, cioè le righe che scrive
   `CHOPPER_TUNE SAVE=1`.
2. Nuove opzioni `hstrt` e `hend` per impostare l'isteresi a mano (tutte e due o nessuna).
3. Priorità: misurato, poi manuale, poi calcolato.
4. Ogni set di registri viene controllato con i limiti del datasheet **prima**
   di scrivere nel driver. Un set non valido ferma Klipper con un messaggio chiaro.
5. Due correzioni discusse nella issue #339 dell'originale: `TOFF=1` ora
   richiede `TBL>=2` (prima bastava 1) e il clock di riserva di TMC2208/2209 è
   12 MHz (prima 12,5).
6. `AUTOTUNE_TMC` accetta `HSTRT=`, `HEND=` e `MEASURED=0|1` e risponde
   sempre con i valori applicati e la loro origine.
7. `printer["autotune_tmc stepper_x"]` espone i valori applicati e la loro
   origine (`source`), utile nelle macro.

## Installazione

### Nuova installazione (autotune non ancora installato)

Clona in una cartella chiamata `klipper_tmc_autotune`: lo script di installazione cerca quel nome.

```bash
cd ~ && git clone -b hybrid https://github.com/quser01/klipper_tmc_autotune_hybrid.git klipper_tmc_autotune
bash ~/klipper_tmc_autotune/install.sh
```

Poi segui il README dell'originale per aggiungere le sezioni `[autotune_tmc ...]`.

### Passare a questo fork da un autotune già installato

1. Controlla che la cartella non abbia modifiche locali:

    ```bash
    cd ~/klipper_tmc_autotune
    git status
    ```

    Deve dire `nothing to commit, working tree clean`. Se elenca file
    modificati, sistemali prima, altrimenti il passo successivo fallisce.

2. Collega la cartella al fork e passa al ramo `hybrid`:

    ```bash
    git remote set-url origin https://github.com/quser01/klipper_tmc_autotune_hybrid.git
    git fetch origin
    git checkout -B hybrid origin/hybrid
    ```

    Non serve rilanciare `install.sh`: i collegamenti dentro Klipper puntano già a questa cartella.

### Aggiornamenti con Moonraker

In `moonraker.conf`:

```ini
[update_manager klipper_tmc_autotune]
type: git_repo
channel: dev
path: ~/klipper_tmc_autotune
origin: https://github.com/quser01/klipper_tmc_autotune_hybrid.git
primary_branch: hybrid
managed_services: klipper
install_script: install.sh
```

Se autotune era già installato basta cambiare `origin` e `primary_branch`.

### Riavvio e controllo

`RESTART` non basta, perché non ricarica il codice Python.

```bash
sudo systemctl restart moonraker
sudo systemctl restart klipper
grep -c measured_chopper ~/klipper_tmc_autotune/autotune_tmc.py   # deve essere > 0
```

Klipper deve ripartire senza errori. A questo punto si comporta ancora come
l'autotune originale: il chopper misurato si usa solo dopo i passi seguenti.

## Misura del chopper

La misura va fatta con autotune **spento** sui motori da misurare:
chopper-autotune non salva su un motore gestito da autotune, e il CoolStep di
autotune abbasserebbe la corrente durante la misura.

1. Installa chopper-autotune (una volta sola, alla fine Klipper si riavvia):

    ```bash
    cd ~ && git clone https://github.com/anton-vinogradov/chopper-autotune && bash ./chopper-autotune/install.sh
    ```

2. Commenta con `#` ogni riga delle sezioni `[autotune_tmc ...]` dei motori da
   misurare, di solito X e Y (`stepper_x`, `stepper_y`, più `stepper_x1` e
   `stepper_y1` con l'AWD). Lascia come sono Z ed estrusore.
3. **Solo con homing sensorless su questi assi:** aggiungi nella sezione
   `[tmc...]` la soglia StallGuard che usava autotune (`driver_SGT` su
   TMC5160, TMC2240 e TMC2130; `driver_SGTHRS` su TMC2209), con il valore di
   `sgt` / `sg4_thrs` di autotune (predefiniti 1 / 40). Senza, l'homing può
   non fermarsi.
4. Riavvia Klipper, poi `G28`. Con due motori sullo stesso asse l'ugello deve
   stare ad almeno 5 mm dal piatto: se serve, `G1 Z10`.
5. Prova a secco, non muove niente:

    ```
    CHOPPER_TUNE DRY_RUN=1
    ```

    Leggi cosa stampa (driver, movimenti, distanza dai bordi, avvisi sul
    calore) e risolvi i problemi che segnala.
6. Misura e salva:

    ```
    CHOPPER_TUNE SAVE=1
    ```

    Dura circa 20 minuti. Con l'AWD tutti i motori X/Y restano sotto corrente
    per tutta la prova: tieni d'occhio la temperatura dei driver. Alla fine il
    tool scrive le righe `driver_*` nelle sezioni `[tmc...]` e riavvia Klipper,
    che azzera l'homing.
7. Controlla che le sezioni `[tmc...]` dei motori misurati abbiano le nuove
   righe `driver_*`. Il log completo è in
   `~/printer_data/config/chopper-autotune/tune.log`.

## Riattivare autotune con il chopper misurato

Togli i `#` dalle sezioni `[autotune_tmc ...]` e aggiungi in ognuna
`measured_chopper: True`:

```ini
[autotune_tmc stepper_x]
motor: <il tuo motore>
voltage: <la tensione di alimentazione>
measured_chopper: True
```

- Togli da queste sezioni `tbl`, `toff`, `tpfd`, `hstrt` e `hend`, se ci
  sono: con `measured_chopper` attivo Klipper si ferma se li trova.
- Lascia le righe `driver_*` nelle sezioni `[tmc...]`: ora autotune legge il
  chopper da lì.
- Il `driver_SGT` aggiunto al punto 3 può restare: all'avvio autotune lo
  riscrive con il suo `sgt`.

Poi `RESTART` (qui basta, il codice non è cambiato) e `G28`.

## Verifica e confronto

Per ogni motore misurato scrivi:

```
AUTOTUNE_TMC STEPPER=stepper_x
```

La risposta compare nella console di Mainsail o Fluidd, subito sotto il comando:

```
autotune stepper_x: chopper measured tbl=1 toff=3 tpfd=0 hstrt=2 hend=4
```

- Deve dire `measured`. Se dice `computed`, su quel motore
  `measured_chopper: True` non è attivo.
- I numeri devono essere uguali alle righe `driver_*` della sezione `[tmc...]`
  di quel motore.

Gli stessi valori sono anche in `klippy.log`, scritti a ogni avvio di Klipper.
Cerca `chopper`: trovi righe come
`autotune_tmc stepper_x chopper {'tbl': 1, 'toff': 3, ..., 'source': 'measured'}`.
È utile se Klipper non parte e la console non è disponibile.

**Confronto A/B.** Cambia sempre **tutti** i motori dello stesso asse insieme:
due motori dello stesso asse con chopper diversi lavorano uno contro l'altro.

```
AUTOTUNE_TMC STEPPER=stepper_x MEASURED=0
AUTOTUNE_TMC STEPPER=stepper_x1 MEASURED=0
```

Stampa lo stesso pezzo di prova con `MEASURED=0` e con `MEASURED=1` e
confronta rumore e superfici. Il cambio vale fino al prossimo riavvio.

## Tornare indietro, rifare la misura, problemi comuni

- **Tornare al chopper calcolato:** togli `measured_chopper: True`, poi `RESTART`.
- **Tornare all'autotune originale:** `git -C ~/klipper_tmc_autotune checkout main`,
  in `moonraker.conf` rimetti `origin` a
  `https://github.com/andrewmcgr/klipper_tmc_autotune.git` e
  `primary_branch: main`, poi `sudo systemctl restart klipper`.
- **Rifare la misura** dopo aver cambiato motori, tensione, corrente o
  tensione delle cinghie: ripeti da "Misura del chopper".

| Messaggio o sintomo | Causa | Cosa fare |
|---|---|---|
| `measured_chopper is on, but [tmc... stepper_x] has no driver_TBL` | La misura non è stata salvata per quel motore | Rifai la misura con `SAVE=1` |
| `measured_chopper takes the chopper from ..., remove tbl` | Valori del chopper anche nella sezione autotune | Toglili da `[autotune_tmc]` |
| `measured chopper invalid, toff=1 requires tbl >= 2` | Righe `driver_*` modificate a mano in modo non valido | Rifai la misura o correggi i valori |
| `not saving ...: autotune resets its chopper at start` | `[autotune_tmc]` ancora attivo durante la misura | Commentalo e rifai la misura |
| `computed PWM_OFS=... leaves no headroom` | Calcolo PWM fuori scala con la tua tensione e corrente | Abbassa `run_current` |
| Homing X/Y che non si ferma | Homing sensorless senza soglia StallGuard con autotune spento | Ferma la stampante e aggiungi `driver_SGT` (misura, punto 3) |
| Il motore fischia dopo la misura | Frequenza del chopper nella banda udibile | `CHOPPER_TUNE SAVE=1 SKIP_AUDIBLE=1` |

## Limiti noti

- La misura avviene **senza CoolStep** (corrente piena). In stampa autotune
  riaccende il CoolStep, che abbassa la corrente quando il carico è basso.
  Anche il modello di autotune calcola l'isteresi a corrente piena, quindi
  l'ipotesi è la stessa, ma non è verificata con misure.
- chopper-autotune riduce le vibrazioni a bassa frequenza viste
  dall'accelerometro, non il rumore percepito, e non prova le velocità molto
  basse (da 5 a 10 mm/s).
- Con due motori sullo stesso asse `CHOPPER_TUNE` funziona, ma
  `CHOPPER_CURRENT` e il passo della mappa non ancora (issue #129 di chopper-autotune).

## Tenere il fork aggiornato (manutentore)

1. Su GitHub, sul ramo `main`: **Sync fork → Update branch**.
2. Apri una pull request dentro il fork con base `hybrid` e confronto `main`, poi uniscila (merge).
3. Se GitHub scrive **Can't automatically merge**, l'originale ha cambiato le
   stesse righe: risolvi il conflitto a mano invece di forzare.

## Crediti

- [klipper_tmc_autotune](https://github.com/andrewmcgr/klipper_tmc_autotune)
  di andrewmcgr e contributori, licenza GPL-3.0. Questo fork mantiene la stessa licenza.
- [chopper-autotune](https://github.com/anton-vinogradov/chopper-autotune) di
  anton-vinogradov, licenza MIT. Non è incluso qui: va installato a parte.
