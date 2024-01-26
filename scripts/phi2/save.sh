#!/bin/bash
#SBATCH --account=iris
#SBATCH --partition=iris-hi
#SBATCH --nodes=1
#SBATCH --mem=200G
#SBATCH --gres=gpu:titanrtx:1
#SBATCH --time=240:00:00
#SBATCH --job-name=pythia28-hh-base
#SBATCH --output slurm/%j.out
#SBATCH --mail-type=begin
#SBATCH --mail-type=end
#SBATCH --mail-type=fail
#SBATCH --mail-user=rypark@stanford.edu

source env/bin/activate
ulimit -n 64000

python -u train.py datasets=[ultrafeedback] model.archive=/iris/u/rafailov/cache/rafailov/phi-ultrafeedback-0.01_2024-01-25_14-26-24_300599/LATEST/policy.pt save_as_hf=/iris/u/rypark/cache/rypark/phi2-ultrafeedback-b01-a0 trainer=BasicTrainer debug=true exp_name=phi2-save model=phi2

python -u train.py datasets=[ultrafeedback] model.archive=/iris/u/rafailov/cache/rafailov/phi-ultrafeedback-0.01-a-0.005_2024-01-25_19-33-26_627140/LATEST/policy.pt save_as_hf=/iris/u/rypark/cache/rypark/phi2-ultrafeedback-b01-a05 trainer=BasicTrainer debug=true exp_name=phi2-save model=phi2

python -u train.py datasets=[ultrafeedback] model.archive=/iris/u/rafailov/cache/rafailov/phi-ultrafeedback-0.01-a-0.0025_2024-01-26_00-54-55_827995/LATEST/policy.pt save_as_hf=/iris/u/rypark/cache/rypark/phi2-ultrafeedback-b01-a025 trainer=BasicTrainer debug=true exp_name=phi2-save model=phi2