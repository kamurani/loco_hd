# Run this inside the OpenStructure Docker container.
# Use the following bash command:
#
# docker run --rm --name ost_run \
# -v $SCRIPT_DIR:/home \
# -v $DATA_DIR:/data \
# registry.scicore.unibas.ch/schwede/openstructure casp14_ost_target_script.py
#
# where $SCRIPT_DIR is the directory containing this script (e.g.: $(pwd)) and
# $DATA_DIR is the directory containing the pickled input data for this script.

import pickle
from datetime import datetime

from ost.io import PDBStrToEntity
from ost.mol.alg import scoring


def log_line(prev_log: str, msg: str) -> str:

    dt_now = datetime.now().strftime("[ %Y.%m.%d %H:%M:%S ]")
    new_log = f"{prev_log}{dt_now} {msg}\n"

    return new_log


def main():

    with open(f"/data/filtered_structures.pickle", "rb") as f:
        str_collection = pickle.load(f)

    # A highly nested dict:
    # key1: CASP structure name (e.g.: T1024)
    # key2: prediction number (structure_id) (1...5)
    # key3: either "single" or "per_residue"
    # key4: score name (lddt, gdtts, rmsd...)
    # key5 (only applicable if we are in "per_residue"): residue ID ([chain name]/[resi number]-[resi tlc])
    # value: score value
    measurement_collection = dict()
    log_str = ""

    for idx, (structure_name, structure_bundle) in enumerate(str_collection.items()):

        new_log_line = f"Starting structure bundle {structure_name} ({idx + 1}/{len(str_collection)}):"
        log_str = log_line(log_str, new_log_line)

        reference_structure = PDBStrToEntity(structure_bundle["true"])
        measurement_collection[structure_name] = dict()

        for structure_id, structure_str in structure_bundle.items():

            if structure_id == "true":
                continue

            log_str = log_line(log_str, f"\tStarting with structure id {structure_id}")

            predicted_structure = PDBStrToEntity(structure_str)

            scores = scoring.Scorer(
                reference_structure, predicted_structure,
                resnum_alignments=True,  # must be True for CAD score calculation
            )

            single_measurements, per_residue_measurements = dict(), dict()

            single_measurements["lddt"] = scores.lddt
            single_measurements["rmsd"] = scores.rmsd
            single_measurements["cad_score"] = scores.cad_score
            single_measurements["gdtts"] = scores.gdtts
            single_measurements["tm_score"] = scores.tm_score

            per_residue_measurements["lddt"] = {
                f"{resi.chain.name}/{resi.number}-{resi.name}": scores.local_lddt[resi.chain.name][resi.number]
                for resi in predicted_structure.residues
            }

            per_residue_measurements["cad_score"] = {
                f"{resi.chain.name}/{resi.number}-{resi.name}": scores.local_cad_score[resi.chain.name][resi.number]
                for resi in predicted_structure.residues
            }

            measurement_collection[structure_name][int(structure_id)] = {
                "single": single_measurements,
                "per_residue": per_residue_measurements
            }

            with open(f"/data/ost_results.log", "w") as f:
                f.write(log_str)

    with open(f"/data/ost_results.pickle", "wb") as f:
        pickle.dump(measurement_collection, f)


if __name__ == "__main__":
    main()
