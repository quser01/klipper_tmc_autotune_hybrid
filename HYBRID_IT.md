# klipper_tmc_autotune ibrido: chopper misurato + resto calcolato

Questa versione di `klipper_tmc_autotune` può usare i registri del chopper
**misurati** da [chopper-autotune](https://github.com/anton-vinogradov/chopper-autotune)
invece di quelli **calcolati** dal modello del motore. Tutto il resto lo
continua a gestire autotune come prima.

| Cosa                                    | Chi lo decide                  |
|-----------------------------------------|--------------------------------|
| `tbl`, `toff`, `hstrt`, `hend`, `tpfd`  | chopper-autotune (misura)      |
| StealthChop / PWM (`pwm_grad`, `pwm_ofs`, `pwm_freq`) | autotune (calcolo)   |
| CoolStep, soglie StallGuard             | autotune                       |
| `slope_control` TMC2240, fullstep ad alta velocità | autotune            |
| Corrente (`run_current`)                | tu, con l'aiuto di `CHOPPER_CURRENT` |

## Cosa cambia rispetto all'originale

1. Nuova opzione `measured_chopper: True` nella sezione `[autotune_tmc ...]`.
   Legge `driver_TBL`, `driver_TOFF`, `driver_HSTRT`, `driver_HEND` e
   `driver_TPFD` dalla sezione `[tmc... ...]`, cioè proprio le righe che scrive
   `CHOPPER_TUNE SAVE=1`.
2. Nuove opzioni `hstrt` e `hend` per impostare l'isteresi a mano (vanno messe
   tutte e due).
3. Priorità: misurato, poi manuale, poi calcolato.
4. Ogni set di registri viene controllato con le regole del datasheet **prima**
   di scrivere qualsiasi cosa nel driver. Un set non valido ferma Klipper con un
   messaggio chiaro, invece di finire nel driver.
5. Correzioni di due bug riconosciuti dal manutentore (issue #339):
   `TOFF=1` ora richiede `TBL>=2` (prima bastava 1) e il clock di riserva di
   TMC2208/2209 è 12 MHz (prima 12,5).
6. `AUTOTUNE_TMC` accetta `HSTRT=`, `HEND=` e `MEASURED=0|1`, così puoi
   confrontare dal vivo il chopper calcolato e quello misurato. Risponde
   sempre con i valori applicati e la loro origine.
7. `printer["autotune_tmc stepper_x"]` ora espone i valori applicati, utile
   nelle macro.

## Procedura

1. **Togli autotune dai motori da misurare.** Commenta le sezioni
   `[autotune_tmc stepper_x]`, `[autotune_tmc stepper_x1]`, ecc.
   Serve per due motivi: chopper-autotune rifiuta di salvare su un motore
   gestito da autotune, e il CoolStep di autotune abbassa la corrente durante
   la misura, falsandola.
   - **Se fai homing sensorless:** prima copia nella sezione `[tmc...]` la
     soglia StallGuard che usava autotune (`driver_SGT` su TMC5160/2240/2130,
     `driver_SGTHRS` su TMC2209), altrimenti l'homing sbatte.
2. `RESTART`, poi `G28`, poi `CHOPPER_TUNE SAVE=1`. Alla fine Klipper riparte con
   le righe `driver_*` nuove nelle sezioni `[tmc...]`.
3. **Rimetti autotune** con `measured_chopper: True`:

   ```ini
   [autotune_tmc stepper_x]
   motor: <il tuo motore>
   voltage: 48
   measured_chopper: True
   ```

   Non mettere `tbl`, `toff`, `tpfd`, `hstrt`, `hend` in questa sezione:
   Klipper si fermerebbe segnalando il conflitto.
4. `RESTART` e controlla: `AUTOTUNE_TMC STEPPER=stepper_x` deve rispondere
   `chopper measured ...`.
5. Confronto A/B: `AUTOTUNE_TMC STEPPER=stepper_x MEASURED=0` torna al chopper
   calcolato, `MEASURED=1` torna a quello misurato. Il cambio vale fino al
   prossimo riavvio.

Per rifare la misura in futuro ripeti dal punto 1.

## Limiti da sapere

- La misura avviene **senza CoolStep** (corrente piena). Poi in stampa
  autotune riaccende il CoolStep, che abbassa la corrente quando il carico è
  basso. Anche il modello di autotune calcola l'isteresi a corrente piena,
  quindi l'ipotesi è la stessa, ma non è verificata con misure.
- chopper-autotune ottimizza le vibrazioni a bassa frequenza viste
  dall'accelerometro, non il rumore percepito né le velocità molto basse
  (5 o 10 mm/s).
- Con due motori sullo stesso asse (AWD) `CHOPPER_TUNE` funziona, ma i passi
  `CHOPPER_CURRENT` e mappa non ancora (issue #129 di chopper-autotune).
- Testato con test automatici sulla logica, **non su una stampante reale**.
