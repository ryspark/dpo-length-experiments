import logging
import json
import random
import os
import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm
from datasets import load_dataset
from collections import defaultdict
import seaborn as sns
import matplotlib.pyplot as plt
from throttler import submit_jobs


def load_prompt(pfile, pdir):
    """ Loads prompt from file.  """
    with open(os.path.join(pdir, pfile)) as t:
        prompt = "\n".join(map(str.strip, t.readlines()))

    print(f"loaded {pfile}")
    return prompt


def shuffle(d):
    """
    Shuffle dataset.
    """
    k = list(d.keys())
    random.shuffle(k)
    return {key: d[key] for key in k}


def load_hh():
    """
    Loads HH dataset test split.
    """
    dataset = load_dataset("Anthropic/hh-rlhf", split="test")
    reformatted = {}
    i = 0
    kword = "Assistant:"
    for entry in tqdm(dataset):
        s = entry["chosen"].rfind(kword) + len(kword)
        reformatted[entry["chosen"][:s]] = entry["chosen"][s + 1:]
        i += 1
    print(f"loaded {i} examples from HH test split")
    return reformatted


def load_shp():
    """
    Loads SHP dataset test split.
    """
    dataset = load_dataset("stanfordnlp/SHP", split="test")
    reformatted = {}
    i = 0
    for entry in tqdm(dataset):
        key = "A" if int(entry["labels"]) == 0 else "B"
        prompt = f"\n\nHuman: {entry['history']}\n\nAssistant:"
        reformatted[prompt] = entry[f"human_ref_{key}"]
        i += 1
    print(f"loaded {i} examples from SHP test split")
    return reformatted


def load_samples(sample_dir, to_process=None):
    """
    Get samples from directory and list of json files.
    Returns a dict with keys corresponding to model names, and values
    corresponding to dict of prompt: response pairs.
    """
    if to_process is None:
        to_process = os.listdir(sample_dir)

    sampled = defaultdict(dict)
    kword = "Assistant:"
    for f in to_process:
        if f.endswith(".json"):
            with open(os.path.join(sample_dir, f), "r") as fi:
                tmp = json.load(fi)
                for prompt, v in tmp.items():
                    v = v[0]
                    response = v[v.rfind(kword) + len(kword) + 1:]
                    sampled[f.replace(".json", "")][prompt] = response

    print(f"loaded samples from {len(to_process)} models")
    return sampled


def batch_judge(batch, system, template, key, model_wins, cache_file, gpt_model, seed=None, use_lab_key=False):
    """
    Batch critic judge given quality/brevity template and batch of completions.
    template and key control the quality/brevity prompt to use.
    """
    requests = [
        dict(
            messages=[
                dict(role="system", content=system),
                dict(role="user", content=(a, b, prompt, template, model))
            ],
            model=gpt_model,
            seed=seed,
        )
        for a, b, prompt, model in batch
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    if use_lab_key:
        api_key = os.getenv("LAB_OPENAI_API_KEY", api_key)

    responses = submit_jobs(requests, cache_file=cache_file, api_key=api_key)
    for (*_, a, b, model), judgement in responses.items():
        model_wins[model][key].append((a, b, judgement))


def winrates(
    truth,
    sampled,
    quality,
    brevity,
    system,
    gpt_model,
    cache_file,
    batch_size,
    seed,
    stop,
    use_lab_key
):
    """
    Gets winrates between truth and sampled given critic prompts.
    """
    def do_batch(batch, pbar, model_wins, cache_file, seed):
        batch_judge(batch, system, quality, "quality", model_wins, cache_file, gpt_model, seed, use_lab_key)
        pbar.update(batch_size // 2)

        batch_judge(batch, system, brevity, "brevity", model_wins, cache_file, gpt_model, seed, use_lab_key)
        pbar.update(batch_size // 2)

    model_wins = {}
    stop *= len(sampled)
    pbar = tqdm(total=min(len(truth) * len(sampled), stop))
    batch = []
    i = 0

    for prompt in truth:
        # Get batch so far
        try:
            for model in sampled:
                if model not in model_wins:
                    model_wins[model] = defaultdict(list)
                a, b = sampled[model][prompt], truth[prompt]
                batch.append((a, b, prompt, model))
        except KeyError:
            pass

        # Execute batch
        if len(batch) >= batch_size:
            do_batch(batch, pbar, model_wins, cache_file, seed)
            batch = []
            i += batch_size
            if stop is not None and i > stop:
                break

    if len(batch) > 0 and stop is not None and i <= stop:
        do_batch(batch, pbar, model_wins, cache_file, seed)

    return model_wins


def get_flattened(model_wins):
    """
    Returns flattened dataframe of results with length keys added.
    """
    prefix = ""
    stop = False
    for char in list(model_wins.keys())[0]:
        for model in model_wins:
            if not model.startswith(prefix + char):
                stop = True
        if stop:
            break
        prefix += char

    for model in model_wins:
        print("model:", model)
        for key, scores in model_wins[model].items():
            scores = [tup[-1] for tup in scores]
            print("-" * 20)
            print("metric:", key)
            print("len:   ", len(scores))
            print("mean:  ", np.mean(scores))
            print("std:   ", np.std(scores))
        print("=" * 60)

    flat = []
    for model in model_wins:
        for key, scores in model_wins[model].items():
            for (sampled, truth, score) in scores:
                model = model.replace(prefix, "").strip("_full")
                flat.append({
                    "model": model,
                    "metric": key,
                    "sampled": sampled,
                    "truth": truth,
                    "win": int(score),
                })
    flat = pd.DataFrame(flat)
    arch, ds, *_ = prefix.split("_")

    flat['sampled_len'] = flat['sampled'].apply(lambda x: len(x.split()))
    flat['truth_len'] = flat['truth'].apply(lambda x: len(x.split()))

    return flat, ds


def winrates_bar(flat, ds):
    """
    Bar plot with confidence bars for win rates.
    """
    sns.barplot(flat, x="model", y="win", errorbar="ci", hue="metric")
    plt.title(f"{ds.upper()}: GPT4 winrates for quality (helpfulness) and brevity")
    plt.xlabel("Model ID")
    plt.ylabel("GPT Win Rate")
    plt.tight_layout()
    plt.savefig(f"winrates/{ds.lower()}_bar.png", dpi=200, bbox_inches='tight')


def winrates_scatter(flat, ds):
    """
    Scatter plot with confidence bars for win rates.
    """
    # Compute mean, std, and count for each model and metric
    flat = flat.drop(['sampled', 'truth', 'sampled_len', 'truth_len'], axis=1)
    model_stats = flat.groupby(['model', 'metric']).agg(['mean', 'std', 'count']).reset_index()
    model_stats.columns = ['model', 'metric', 'mean', 'std', 'count']
    model_stats['ci_90'] = model_stats.apply(
        lambda row: 1.645 * (row['std'] / np.sqrt(row['count'])),
        axis=1
    )

    # Separate stats for quality and brevity
    quality_stats = model_stats[model_stats['metric'] == 'quality']
    brevity_stats = model_stats[model_stats['metric'] == 'brevity']

    # Merge the two stats dataframes on model and plot
    merged_stats = pd.merge(quality_stats, brevity_stats, on='model', suffixes=('_quality', '_brevity'))
    plt.figure(figsize=(10, 6))
    for _, row in merged_stats.iterrows():
        plt.errorbar(
            x=row['mean_brevity'],
            y=row['mean_quality'],
            xerr=row['ci_90_brevity'],
            yerr=row['ci_90_quality'],
            fmt='o',
            capsize=5,
            label=row['model']
        )

    plt.xlabel('Mean Brevity Score')
    plt.ylabel('Mean Quality Score')
    plt.title(f'{ds.upper()}: GPT4 winrates for quality (helpfulness) vs brevity (90% CI)')
    plt.legend()
    plt.grid(True)
    plt.savefig(f"winrates/{ds.lower()}_scatter.png", dpi=200, bbox_inches='tight')


def winrates_length(flat, ds):
    """
    Plots average length vs win rates.
    """
    # Get average length for each model and apply 90% CI
    lengths = flat[['model', 'sampled_len']]
    lengths = lengths.groupby(['model']).agg(['mean', 'std', 'count']).reset_index()
    lengths.columns = ['model', 'mean', 'std', 'count']
    lengths['ci_90'] = lengths.apply(
        lambda row: 1.645 * (row['std'] / np.sqrt(row['count'])),
        axis=1
    )

    # Get win rates for each model and apply 90% CI
    flat['win'] = flat['win'].astype(int)
    winrates = flat[['model', 'win']]
    winrates = winrates.groupby(['model']).agg(['mean', 'std', 'count']).reset_index()
    winrates.columns = ['model', 'mean', 'std', 'count']
    winrates['ci_90'] = winrates.apply(
        lambda row: 1.645 * (row['std'] / np.sqrt(row['count'])),
        axis=1
    )

    # Merge with winrates
    merged = pd.merge(lengths, winrates, on='model', suffixes=('_length', '_win'))

    # Plot winrates vs length
    plt.figure(figsize=(10, 6))
    for _, row in merged.iterrows():
        plt.errorbar(
            x=row['mean_length'],
            y=row['mean_win'],
            xerr=row['ci_90_length'],
            yerr=row['ci_90_win'],
            fmt='o',
            capsize=5,
            label=row['model']
        )
    
    plt.xlabel('Mean Response Length')
    plt.ylabel('GPT Win Rate')
    plt.title(f'{ds.upper()}: GPT4 winrates vs. average sample length (90% CI)')
    plt.legend()
    plt.grid(True)
    plt.savefig(f"winrates/{ds.lower()}_length.png", dpi=200, bbox_inches='tight')


def winrates_length_ratio(flat, ds):
    """
    Plot sampled length / truth response length vs win rate.
    """
    flat['len_cmp'] = flat['sampled_len'] / flat['truth_len']
    print(flat['len_cmp'].describe())

    plt.figure(figsize=(10, 6))
    sns.kdeplot(
        data=flat,
        x="len_cmp",
        hue="win",
        linewidth=2,
        common_norm=False,
        common_grid=True,
        palette="Set2",
        fill=True,
        alpha=.5,
    )
    plt.xlabel("Ratio of sampled response length to ground-truth response length")
    plt.ylabel(f"Density (n={len(flat)})")
    plt.axvline(
        flat["len_cmp"].mean(),
        color="black",
        linestyle='--',
    )
    plt.legend(
        [f'Mean length ratio'],
        prop={"size": 15},
        loc='upper left'
    )
    plt.title(f"{ds.upper()}: GPT4 winrates for length ratio")
    plt.savefig(f"winrates/{ds.lower()}_length_ratio.png", dpi=200, bbox_inches='tight')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="gpt-4",
        help="gpt critic model to use"
    )
    parser.add_argument(
        "--dataset",
        default="hh",
        help="dataset to use (hh default)"
    )
    parser.add_argument(
        "--sample_dir",
        default="sampled",
        help="directory with sampled completions"
    )
    parser.add_argument(
        "--sample_files",
        nargs="*",
        help="list of files in sample_dir to load"
    )
    parser.add_argument(
        "--prompt_dir",
        default="./prompts",
        help="prompt directory"
    )
    parser.add_argument(
        "--seed",
        default=1234,
        help="seed for gpt critic"
    )
    parser.add_argument(
        "--cache",
        default=".gptcache",
        help="cache file for gpt responses"
    )
    parser.add_argument(
        "--batch_size",
        default=60,
        help="batch size for parallel calls"
    )
    parser.add_argument(
        "--log_level",
        default="WARNING",
        help="logging level"
    )
    parser.add_argument(
        "--stop",
        default=None,
        type=int,
        help="stop at example i"
    )
    parser.add_argument(
        "--lab_key",
        action="store_true",
        help="use LAB_OPENAI_API_KEY instead of OPENAI_API_KEY"
    )

    args = parser.parse_args()
    random.seed(args.seed)
    logging.basicConfig(level=args.log_level)

    quality = load_prompt("quality.prompt", args.prompt_dir)
    brevity = load_prompt("brevity.prompt", args.prompt_dir)
    system = load_prompt("system.prompt", args.prompt_dir)

    sampled = load_samples(args.sample_dir, args.sample_files)
    truth = locals()[f"load_{args.dataset}"]()
    truth = shuffle(truth)

    flat, ds = get_flattened(
        winrates(
            truth,
            sampled,
            quality,
            brevity,
            system,
            args.model,
            args.cache,
            args.batch_size,
            args.seed,
            args.stop,
            args.lab_key
        )
    )
    for plotter in [winrates_bar, winrates_scatter, winrates_length, winrates_length_ratio]:
        plotter(flat, ds)
