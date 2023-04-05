use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

use rayon::prelude::*;
use rayon::iter::ParallelIterator;

#[cfg(test)]
mod weight_function_utests;
mod weight_function;
pub use weight_function::WeightFunction;

#[cfg(test)]
mod pmf_utests;
mod pmf;
use pmf::PMFSystem;

#[cfg(test)]
mod locohd_utests;

mod primitive_atom;
pub use primitive_atom::PrimitiveAtom;

mod utils;

#[pyclass]
pub struct LoCoHD {

    #[pyo3(get, set)]
    categories: Vec<String>,

    w_func: WeightFunction
}

#[pymethods]
impl LoCoHD {

    #[new]
    pub fn new(categories: Vec<String>, w_func: WeightFunction) -> Self {
        Self { categories, w_func }
    }

    /// Calculates the hellinger integral between two environments belonging to two anchor points.
    pub fn from_anchors(&self, 
        seq_a: Vec<String>, 
        seq_b: Vec<String>, 
        dists_a: Vec<f64>, 
        dists_b: Vec<f64>) -> PyResult<f64> 
    {

        // Check input validity.
        if seq_a.len() != dists_a.len() || seq_b.len() != dists_b.len() {
            let err_msg = "Lists seq and dists must have equal lengths!".to_owned();
            return Err(PyValueError::new_err(err_msg));
        }
        if dists_a[0] != 0. || dists_b[0] != 0. {
            let err_msg = "The dists list must start with a distance of 0!".to_owned();
            return Err(PyValueError::new_err(err_msg));
        }

        // Create the probability mass functions (PMFs) and add the first CAT-observations
        // to them (the first element from seq_a and seq_b).
        let mut pmf_system = PMFSystem::new(&self.categories);
        pmf_system.update_pmf1(&seq_a[0])?;
        pmf_system.update_pmf2(&seq_b[0])?;

        // Initialize the parallel indices, the hellinger integral, and a buffer for the previous distance. 
        let mut idx_a: usize = 0;
        let mut idx_b: usize = 0;
        let mut h_integral: f64 = 0.;
        let mut dist_buffer: f64 = 0.;

        // Main loop. This collates (like in merge sort) the distances, while calculating the hellinger integral.
        while idx_a < seq_a.len() - 1 && idx_b < seq_b.len() - 1 {

            // Calculate Hellinger distance.            
            let current_hdist = pmf_system.hellinger_dist()?;

            // Select the next smallest distance from dists_a and dists_b.
            // Also, add the new observed CAT to the PMFs.
            let new_dist = if dists_a[idx_a + 1] < dists_b[idx_b + 1] {

                idx_a += 1;
                pmf_system.update_pmf1(&seq_a[idx_a])?;
                dists_a[idx_a]

            } else if dists_a[idx_a + 1] > dists_b[idx_b + 1] {

                idx_b += 1;
                pmf_system.update_pmf2(&seq_b[idx_b])?;
                dists_b[idx_b]

            } else if dists_a[idx_a + 1] == dists_b[idx_b + 1] {

                idx_a += 1;
                idx_b += 1;
                pmf_system.update_pmf1(&seq_a[idx_a])?;
                pmf_system.update_pmf2(&seq_b[idx_b])?;
                dists_a[idx_a]

            } else { unreachable!(); };

            // Increment the integral and assign the distance buffer to the new distance.
            let delta_w = self.w_func.integral_range(dist_buffer, new_dist)?;
            h_integral +=  delta_w * current_hdist;
            dist_buffer = new_dist;
        }

        // Finalizing loops. This happens if one of the lists is finished before the other.
        if idx_b < seq_b.len() - 1 {

            let current_hdist = pmf_system.hellinger_dist()?;

            // In this case, the dists_a list is surely finished (see prev. while loop condition), but
            // the dists_b list is not.
            idx_b += 1;
            let delta_w = self.w_func.integral_range(dists_a[dists_a.len() - 1], dists_b[idx_b])?;
            h_integral += delta_w * current_hdist;

            pmf_system.update_pmf2(&seq_b[idx_b])?;

            // Finishing the dists_b list.
            while idx_b < seq_b.len() - 1 {

                idx_b += 1;

                let current_hdist = pmf_system.hellinger_dist()?;
                let delta_w = self.w_func.integral_range(dists_b[idx_b - 1], dists_b[idx_b])?;
                h_integral += delta_w * current_hdist;

                pmf_system.update_pmf2(&seq_b[idx_b])?;
            }

            // Last integral until infinity.
            let current_hdist = pmf_system.hellinger_dist()?;
            let delta_w = self.w_func.integral_range(dists_b[dists_b.len() - 1], f64::INFINITY)?;
            h_integral += delta_w * current_hdist;

        } else if idx_a < seq_a.len() - 1 {

            let current_hdist = pmf_system.hellinger_dist()?;

            // In this case, the dists_b list is finished, but dists_a is not.
            idx_a += 1;
            let delta_w = self.w_func.integral_range(dists_b[dists_b.len() - 1], dists_a[idx_a])?;
            h_integral += delta_w * current_hdist;

            pmf_system.update_pmf1(&seq_a[idx_a])?;

            // Finishing the dists_a list.
            while idx_a < seq_a.len() - 1 {

                idx_a += 1;

                let current_hdist = pmf_system.hellinger_dist()?;
                let delta_w = self.w_func.integral_range(dists_a[idx_a - 1], dists_a[idx_a])?;
                h_integral += delta_w * current_hdist;

                pmf_system.update_pmf1(&seq_a[idx_a])?;
            }

            // Last integral until infinity.
            let current_hdist = pmf_system.hellinger_dist()?;
            let delta_w = self.w_func.integral_range(dists_a[dists_a.len() - 1], f64::INFINITY)?;
            h_integral += delta_w * current_hdist;

        } else if idx_a == seq_a.len() - 1 && idx_b == seq_b.len() - 1 {

            // Last integral until infinity.
            // In this case, dists_a[dists_a.len() - 1] == dists_b[dists_b.len() - 1]
            let current_hdist = pmf_system.hellinger_dist()?;
            let delta_w = self.w_func.integral_range(dists_a[dists_a.len() - 1], f64::INFINITY)?;
            h_integral += delta_w * current_hdist;

        } else { unimplemented!(); }

        Ok(h_integral)
    }

    /// Compares two structures with a given sequence pair of categories (seq_a and seq_b) 
    /// and a given distance matrix pair (dmx_a and dmx_b).
    fn from_dmxs(&self, 
        seq_a: Vec<String>, 
        seq_b: Vec<String>, 
        dmx_a: Vec<Vec<f64>>, 
        dmx_b: Vec<Vec<f64>>) -> PyResult<Vec<f64>>
    {

        // Check input validity.
        if dmx_a.len() != dmx_b.len() {

            let err_msg = format!(
                "Expected matrices with the same lengt, got lengths {} and {}!", 
                dmx_a.len(), 
                dmx_b.len()
            );
            return Err(PyValueError::new_err(err_msg));
        }

        let (output_ok, output_err): (Vec<_>, Vec<_>) = dmx_a
            .par_iter()
            .zip(&dmx_b)
            .map(|(row_a, row_b)| {
                let (current_dists_a, current_seq_a) = utils::sort_together(row_a, &seq_a);
                let (current_dists_b, current_seq_b) = utils::sort_together(row_b, &seq_b);
                self.from_anchors(current_seq_a, current_seq_b, current_dists_a, current_dists_b)
            })
            .partition(Result::is_ok);

        if output_err.len() > 0 {
            let err_msg = "The from_anchors function returned an error during the LoCoHD calculations!".to_owned();
            return Err(PyValueError::new_err(err_msg));
        }

        let output_ok = output_ok.into_iter().map(|x| x.unwrap()).collect();

        Ok(output_ok)

    }

    /// Compares two structures with a given sequence pair of categories (coords_a and coords_b) 
    /// and a given coordinate-set pair (dmx_a and dmx_b). It calculates the distance matrices
    /// with the L2 (Euclidean) metric.
    fn from_coords(&self, 
        seq_a: Vec<String>, 
        seq_b: Vec<String>, 
        coords_a: Vec<Vec<f64>>, 
        coords_b: Vec<Vec<f64>>) -> PyResult<Vec<f64>>
    {

        let dmx_a = utils::calculate_distance_matrix(&coords_a);
        let dmx_b = utils::calculate_distance_matrix(&coords_b);

        self.from_dmxs(seq_a, seq_b, dmx_a, dmx_b)
    }

    /// Compares two structures with a given primitive atom sequence pair.
    fn from_primitives(&self, 
        prim_a: Vec<PrimitiveAtom>, 
        prim_b: Vec<PrimitiveAtom>, 
        anchor_pairs: Vec<(usize, usize)>, 
        only_hetero_contacts: bool,
        threshold_distance: f64) -> Vec<f64> 
    {

        let mut dmx_a: HashMap<(usize, usize), f64> = HashMap::new();
        let mut dmx_b: HashMap<(usize, usize), f64> = HashMap::new();

        let mut output = vec![];
        
        for &(idx_a1, idx_b1) in anchor_pairs.iter() {

            let mut dists_a: Vec<f64> = vec![];
            let mut seq_a: Vec<String> = vec![];

            for idx_a2 in 0..prim_a.len() {

                if idx_a1 == idx_a2 {
                    dists_a.push(0.);
                    seq_a.push(prim_a[idx_a1].primitive_type.clone());
                    continue;
                }

                if prim_a[idx_a1].tag == prim_a[idx_a2].tag && only_hetero_contacts {
                    continue;
                }

                let idx_pair = if idx_a1 > idx_a2 { (idx_a2, idx_a1) } else { (idx_a1, idx_a2) };

                let dist = match dmx_a.get(&idx_pair) {
                    Some(&dist) => dist,
                    None => {
                        let dist = utils::euclidean_distance(&prim_a[idx_a1].coordinates, &prim_a[idx_a2].coordinates);
                        dmx_a.insert(idx_pair, dist);
                        dist
                    }
                };

                if dist > threshold_distance {
                    continue;
                }

                dists_a.push(dist);                
                seq_a.push(prim_a[idx_a2].primitive_type.clone());
            }

            let mut dists_b: Vec<f64> = vec![];
            let mut seq_b: Vec<String> = vec![];

            for idx_b2 in 0..prim_b.len() {

                if idx_b1 == idx_b2 {
                    dists_b.push(0.);
                    seq_b.push(prim_b[idx_b1].primitive_type.clone());
                    continue;
                }

                if prim_b[idx_b1].tag == prim_b[idx_b2].tag && only_hetero_contacts {
                    continue;
                }

                let idx_pair = if idx_b1 > idx_b2 { (idx_b2, idx_b1) } else { (idx_b1, idx_b2) };

                let dist = match dmx_b.get(&idx_pair) {
                    Some(&dist) => dist,
                    None => {
                        let dist = utils::euclidean_distance(&prim_b[idx_b1].coordinates, &prim_b[idx_b2].coordinates);
                        dmx_b.insert(idx_pair, dist);
                        dist
                    }
                };

                if dist > threshold_distance {
                    continue;
                }

                dists_b.push(dist);
                seq_b.push(prim_b[idx_b2].primitive_type.clone());
            }

            let (dists_a, seq_a) = utils::sort_together(&dists_a, &seq_a);
            let (dists_b, seq_b) = utils::sort_together(&dists_b, &seq_b);

            output.push(
                self.from_anchors(seq_a, seq_b, dists_a, dists_b).unwrap()
            );
        }

        output
    }
}