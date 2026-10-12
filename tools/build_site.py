"""Assemble the static viewer and optional separately maintained website content."""
from argparse import ArgumentParser
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
parser = ArgumentParser()
parser.add_argument('--article-dir', type=Path)
args = parser.parse_args()
destination = ROOT / 'dist'
if destination.exists():
    shutil.rmtree(destination)
destination.mkdir()
for name in ['index.html', '.nojekyll', 'explorer', 'measurements', 'assets']:
    source = ROOT / name
    if source.is_dir():
        if name == 'measurements':
            shutil.copytree(source / 'recorded', destination / name / 'recorded')
        else:
            shutil.copytree(source, destination / name)
    else:
        shutil.copyfile(source, destination / name)
if args.article_dir:
    target = destination / 'article'
    target.mkdir()
    for name in ['index.html', 'article.html', 'body.html', 'article.md',
                 'delivery.css', 'delivery.js', 'title.txt', 'subtitle.txt',
                 'images.json', 'article-package.zip']:
        shutil.copyfile(args.article_dir / name, target / name)
    (target / 'images').mkdir()
    for name in ['approaches.png', 'experiment.png', 'results.png', 'answers.png']:
        shutil.copyfile(args.article_dir / 'images' / name, target / 'images' / name)
print('Static site assembled in dist/.')
