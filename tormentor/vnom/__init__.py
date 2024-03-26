from Bio import SeqIO
import subprocess
import os

def run_vnom(fasta_preffix, max_length=2000):
    command = (
        'python vnom/VNom.py '
        f'-i {fasta_preffix} '
        f'-max {max_length} '
        '-CF_k 10 '
        '-CF_simple 0 '
        '-CF_tandem 1 '
        '-USG_vs_all 1 '
    )
    return subprocess.call(command, shell=True)

def split_vnom_candidates(fasta_file, output_directory, min_length, max_length):
    files = []
    for r, record in enumerate(SeqIO.parse(fasta_file, 'fasta')):
        file = os.path.join(output_directory, f'{r+1}.fasta')
        record.id          = f'obelisk-candidate:{r+1}'
        record.description = f'obelisk-candidate:{r+1}'
        if min_length <= len(record.seq) <= max_length:
            SeqIO.write([record], open(file, 'w'), 'fasta')
        files.append(file)
    return files