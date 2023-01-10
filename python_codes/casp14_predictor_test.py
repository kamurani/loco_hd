import tarfile
import codecs
import pickle
import os

import matplotlib.pyplot as plt
import numpy as np

from Bio.PDB.Structure import Structure

from pathlib import Path
from typing import List, Dict
from matplotlib.patches import Rectangle
from scipy.stats import spearmanr

from loco_hd import LoCoHD, PrimitiveAtom
from atom_converter_utils import PrimitiveAssigner, PrimitiveAtomTemplate


# Set the necessary paths. The available predictor keys are the following:
# AF2: TS427, BAKER: TS473, BAKER-experimental: TS403, FEIG-R2: TS480, Zhang: TS129
LDDT_TARS_PATH = Path("/home/fazekaszs/CoreDir/PhD/PDB/casp14/lDDTs")
PREDICTOR_KEY = "TS480"
WORKDIR = Path(f"./workdir/{PREDICTOR_KEY}_results")


def prat_to_pra(prat: PrimitiveAtomTemplate) -> PrimitiveAtom:

    resi_id = prat.atom_source.source_residue
    resname = prat.atom_source.source_residue_name
    source = f"{resi_id[2]}/{resi_id[3][1]}-{resname}"
    return PrimitiveAtom(prat.primitive_type, source, prat.coordinates)


def lddt_from_text(text: str):

    text = text.split("\n")
    header_text = "Chain	ResName	ResNum	Asses.	Q.Prob.	Score"
    start_idx = next(idx for idx in range(len(text)) if text[idx].startswith(header_text))
    text = text[start_idx + 1:]
    text = list(map(lambda line: line.split("\t"), text))
    text = {f"{line[0]}/{line[2]}-{line[1]}": float(line[5]) for line in text if len(line) != 1 and line[5] != "-"}
    return text


def read_lddt_values(structure_key: str) -> Dict[str, Dict[str, float]]:

    lddt_dict = dict()
    with tarfile.open(LDDT_TARS_PATH / f"{structure_key}.tgz") as tf:
        tf_members = tf.getmembers()
        tf_members = list(filter(lambda m: f"{structure_key}{PREDICTOR_KEY}_" in m.name, tf_members))
        for tf_member in tf_members:
            f = tf.extractfile(tf_member)
            content = codecs.getreader("utf-8")(f).read()
            content = lddt_from_text(content)
            member_key = tf_member.name.split("/")[2].replace(".lddt", "")
            lddt_dict[member_key] = content
            f.close()

    return lddt_dict


def get_plot_alpha(lchd_scores, lddt_scores):

    area_per_tick = np.max(lchd_scores) - np.min(lchd_scores)
    area_per_tick *= np.max(lddt_scores) - np.min(lddt_scores)
    area_per_tick /= len(lddt_scores)
    area_per_tick *= 1E3

    return area_per_tick if area_per_tick < 1. else 1.


def create_plot(key: str, lchd_scores: List[float], lddt_scores: List[float], spr: float):

    fig, ax = plt.subplots()

    ax.scatter(lchd_scores, lddt_scores,
               alpha=get_plot_alpha(lchd_scores, lddt_scores),
               edgecolors="none", c="red")

    lchd_range = np.arange(0, 0.5, 0.05)
    lddt_range = np.arange(0, 1, 0.1)

    ax.set_xticks(lchd_range, labels=[f"{tick:.0%}" for tick in lchd_range])
    ax.set_yticks(lddt_range, labels=[f"{tick:.0%}" for tick in lddt_range])
    ax.set_xlim(0, 0.5)
    ax.set_ylim(0, 1)

    ax.set_xlabel("LoCoHD score")
    ax.set_ylabel("lDDT score")
    fig.suptitle(key)
    legend_handles = [Rectangle((0, 0), 1, 1, fc="white", ec="white", lw=0, alpha=0), ] * 3
    legend_labels = list()
    legend_labels.append(f"SpR = {spr:.5f}")
    legend_labels.append(f"mean LoCoHD = {np.mean(lchd_scores):.1%}")
    legend_labels.append(f"mean lDDT = {np.mean(lddt_scores):.1%}")
    ax.legend(legend_handles, legend_labels,
              loc="upper right", fontsize="small", fancybox=True,
              framealpha=0.7, handlelength=0, handletextpad=0)
    fig.savefig(WORKDIR / f"{key}.png", dpi=300)

    plt.close(fig)


def main():

    # Create the primitive assigner
    primitive_assigner = PrimitiveAssigner(Path("./primitive_typings/all_atom_with_centroid.config.json"))

    # Create the LoCoHD instance.
    lchd = LoCoHD(primitive_assigner.all_primitive_types, ("uniform", [3, 10]))

    # The values in the structures dict are lists of structures, where the first structure
    # in the lists is the true structure, and the rest of them are the predicted structures.
    with open(WORKDIR / f"{PREDICTOR_KEY}_structures.pickle", "rb") as f:
        structures: Dict[str, List[Structure]] = pickle.load(f)

    # For statistics collection.
    spr_values = list()
    median_lddts = list()
    median_lchds = list()

    # For the global histogram.
    hist_range = [[0, 0.5], [0, 1]]
    hist_bins = 100
    hist, hist_xs, hist_ys = np.histogram2d([], [], bins=hist_bins, range=hist_range)

    for structure_key in structures:

        if not os.path.exists(LDDT_TARS_PATH / f"{structure_key}.tgz"):
            continue

        # Read the lDDT values for the current structure. The lddt_dict is a dict of dicts, with
        # the first dict keys being "{structure_key}{PREDICTOR_KEY}_{structure_index}" and the second dict
        # keys being "{chain_index}/{residue_index}-{residue_name}".
        lddt_dict = read_lddt_values(structure_key)

        # Transform the real structure into a list of primitive atoms and get the anchors
        # simultaneously.
        true_pra_templates = primitive_assigner.assign_primitive_structure(structures[structure_key][0])
        anchors = [(idx, idx) for idx, prat in enumerate(true_pra_templates) if prat.primitive_type == "Cent"]
        true_prim_atoms = list(map(prat_to_pra, true_pra_templates))

        # For each predicted structure...
        for pred_idx, structure in enumerate(structures[structure_key][1:]):

            # Transform the predicted structure.
            pred_pra_templates = primitive_assigner.assign_primitive_structure(structure)
            pred_prim_atoms = list(map(prat_to_pra, pred_pra_templates))

            # Calculate LoCoHD score (only_hetero_contacts = True, distance_cutoff = 10).
            lchd_scores = lchd.from_primitives(true_prim_atoms, pred_prim_atoms, anchors, True, 10)

            # Collecting the lDDT scores.
            lddt_scores = list()
            key1 = f"{structure_key}{PREDICTOR_KEY}_{pred_idx + 1}"
            for anchor, _ in anchors:
                key2 = true_prim_atoms[anchor].id
                lddt_scores.append(lddt_dict[key1][key2])

            # Calculating the Spearman's correlation coefficient
            current_spr = spearmanr(lchd_scores, lddt_scores).correlation

            # Updating the statistics.
            spr_values.append(current_spr)
            median_lchds.append(np.median(lchd_scores))
            median_lddts.append(np.median(lddt_scores))

            # Plotting.
            create_plot(key1, lchd_scores, lddt_scores, current_spr)

            # Update histogram.
            new_hist, _, _ = np.histogram2d(lchd_scores, lddt_scores, bins=hist_bins, range=hist_range)
            hist += new_hist

            # Saving the histogram.
            fig, ax = plt.subplots()
            fig.suptitle(f"Distribution of Scores for\nContestant {PREDICTOR_KEY}")
            ax.imshow(hist[:, ::-1].T, cmap="hot")
            ticks = list(range(0, hist_bins, 10))
            ax.set_xticks(ticks, labels=[f"{hist_xs[idx]:.0%}" for idx in ticks])
            ax.set_yticks(ticks, labels=[f"{hist_ys[-idx-1]:.0%}" for idx in ticks])
            ax.set_xlabel("LoCoHD score")
            ax.set_ylabel("lDDT score")
            fig.savefig(WORKDIR / "full_hist.png", dpi=300)
            plt.close(fig)

            print(f"{key1} done...")

    # Saving statistics.
    out_str = ""
    out_str += f"Mean SpR: {np.mean(spr_values)}\n"
    out_str += f"Median SpR: {np.median(spr_values)}\n"
    out_str += f"Std SpR: {np.std(spr_values)}\n"
    out_str += f"Min SpR: {np.min(spr_values)}\n"
    out_str += f"Max SpR: {np.max(spr_values)}\n"

    out_str += f"Mean median lDDT: {np.mean(median_lddts)}\n"
    out_str += f"Median median lDDT: {np.median(median_lddts)}\n"
    out_str += f"Std median lDDT: {np.std(median_lddts)}\n"
    out_str += f"Min median lDDT: {np.min(median_lddts)}\n"
    out_str += f"Max median lDDT: {np.max(median_lddts)}\n"

    out_str += f"Mean median LoCoHD: {np.mean(median_lchds)}\n"
    out_str += f"Median median LoCoHD: {np.median(median_lchds)}\n"
    out_str += f"Std median LoCoHD: {np.std(median_lchds)}\n"
    out_str += f"Min median LoCoHD: {np.min(median_lchds)}\n"
    out_str += f"Max median LoCoHD: {np.max(median_lchds)}\n"

    with open(WORKDIR / "statistics.txt", "w") as f:
        f.write(out_str)


if __name__ == "__main__":
    main()
