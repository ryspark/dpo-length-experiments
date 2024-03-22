#!/bin/bash
#SBATCH --account=iris
#SBATCH --partition=iris-hi
#SBATCH --nodes=1
#SBATCH --mem=128G
#SBATCH --gres=gpu:a40:4
#SBATCH --time=240:00:00
#SBATCH --job-name=uf-sample
#SBATCH --output slurm/%j.out
#SBATCH --mail-type=begin
#SBATCH --mail-type=end
#SBATCH --mail-type=fail
#SBATCH --mail-user=rypark@stanford.edu

source env/bin/activate
ulimit -n 64000

cd ../FastChat/fastchat/llm_judge/
python gen_model_answer.py --model-path alignment-handbook/zephyr-7b-sft-full --model-id zephyr7b-sft-beam1 --num-gpus-per-model 4 --num_beams 1 --no_repeat_ngram_size 0 --num-gpus-total 4
python gen_model_answer.py --model-path alignment-handbook/zephyr-7b-sft-full --model-id zephyr7b-sft-beam5 --num-gpus-per-model 4 --num_beams 5 --no_repeat_ngram_size 0 --num-gpus-total 4
python gen_model_answer.py --model-path alignment-handbook/zephyr-7b-sft-full --model-id zephyr7b-sft-beam10 --num-gpus-per-model 4 --num_beams 10 --no_repeat_ngram_size 0 --num-gpus-total 4
python gen_model_answer.py --model-path alignment-handbook/zephyr-7b-sft-full --model-id zephyr7b-sft-beam20 --num-gpus-per-model 4 --num_beams 20 --no_repeat_ngram_size 0 --num-gpus-total 4

