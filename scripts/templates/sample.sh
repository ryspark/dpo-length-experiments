#!/bin/bash
#SBATCH --account=iris
#SBATCH --partition=iris-hi
#SBATCH --nodes=1
#SBATCH --mem=128G
#SBATCH --gres=gpu:a40:1
#SBATCH --time=240:00:00
#SBATCH --job-name={dataset_id}-sample
#SBATCH --output slurm/%j.out
#SBATCH --mail-type=begin
#SBATCH --mail-type=end
#SBATCH --mail-type=fail
#SBATCH --mail-user=rypark@stanford.edu

source env/bin/activate
ulimit -n 64000

python -u train.py model.archive={model_archive} eval_batch_size={batch_size} sample_only=true samples_per_prompt=1 sample_path={sample_path} exp_name={dataset_id}-sample n_eval_model_samples=256 debug=true trainer=BasicTrainer datasets=[{dataset}] max_length={max_len} model={model} num_beams={num_beams} repetition_penalty={repetition_penalty} top_k={top_k} penalty_alpha={penalty_alpha} temperature={temperature} no_repeat_ngram_size={no_repeat_ngram_size} top_p={top_p} loss.beta={beta} loss.alpha={alpha}
