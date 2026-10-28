"""Figuras de experimentos; matplotlib se instala solo para este comando."""
import json
from .io import ROOT


def figures(runs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = ROOT / 'artifacts/figures'
    output.mkdir(parents=True, exist_ok=True)
    reports = [json.loads((path / 'summary.json').read_text()) for path in runs]
    configs = [json.loads((path / 'manifest.json').read_text()) for path in runs]
    # Refuse to compare different evaluation populations.
    signatures = {(c['questions_sha256'], c['splits_sha256'], c['split'], c['language'], c['limit']) for c in configs}
    if len(signatures) != 1:
        raise ValueError('Las figuras comparativas requieren mismo conjunto e idioma')
    labels = [c['config'] + '\n' + c['run_id'][-8:] for c in configs]
    scores = [r['execution_accuracy'] for r in reports]
    if any(x is None for x in scores):
        raise ValueError('No hay referencias evaluables en alguna corrida')
    errors = [[max(0, s-r['accuracy_ci95'][0]) for s, r in zip(scores, reports)], [max(0, r['accuracy_ci95'][1]-s) for s, r in zip(scores, reports)]]
    fig, ax = plt.subplots(figsize=(max(7, 2*len(runs)), 4))
    ax.bar(labels, scores, yerr=errors, capsize=5, color='#187b8d')
    ax.set(ylabel='Exactitud por ejecución (IC 95%)', ylim=(0, 1))
    fig.tight_layout()
    fig.savefig(output / 'execution_accuracy.png', dpi=180)
    plt.close(fig)
    usable = [(label, r) for label, r in zip(labels, reports) if r['cost_observed_n'] == r['n']]
    if usable:
        fig, ax = plt.subplots(figsize=(7, 4))
        for label, r in usable:
            x = r['cost_observed_total_usd'] / r['n']
            ax.scatter(x, r['execution_accuracy'])
            ax.annotate(label, (x, r['execution_accuracy']))
        ax.set(xlabel='USD por pregunta', ylabel='Exactitud por ejecución')
        fig.tight_layout()
        fig.savefig(output / 'cost_quality.png', dpi=180)
        plt.close(fig)
    print(output)
