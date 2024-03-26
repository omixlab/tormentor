from tormentor.quality_control import run_fastp
from tormentor.assembly import run_spades, filter_and_rename_spades_transcripts
from tormentor.vnom import run_vnom, split_vnom_candidates
from tormentor.annotation import run_prodigal, correct_contig, run_cmscan, add_rfam_sites_to_record
from tormentor.secondary_structure import run_rnafold, compute_self_pairing_percent
from argparse import ArgumentParser
from Bio import SeqIO
from BCBio import GFF

import os

def main():

    argument_parser = ArgumentParser(description="An obelisk prediction and annotation pipeline from stranded RNA-Seq data")
    argument_parser.add_argument('--reads', nargs=2, metavar='<FASTQ file>', help='forward and reverse FASTQ files from stranded RNA-Seq')
    argument_parser.add_argument('-o', '--output', help='output directory')
    argument_parser.add_argument('-s', '--minimum-self-pairing-percent', help='minimum percent in secondary structure', default=0.5, type=float)
    argument_parser.add_argument('--threads', help='number of CPU threads to use', default=4)
    argument_parser.add_argument('--min-qual', help='minimal quality of reads in Phred score', default=30)
    argument_parser.add_argument('--stranded-type', choices=['fr', 'rf'], default=None, help='stranded library layout (for rnaSPAdes)')
    argument_parser.add_argument('--min-len', default=900, type=int, help='min length for predicted obelisks')
    argument_parser.add_argument('--max-len', default=2000, type=int, help='max length for predicted obelisks')
    argument_parser.add_argument('--cm-directory', help='rfam directory containing the alpha_body.cm and alpha_tip.com files', required=True)
    arguments = argument_parser.parse_args()

    fastp_directory               = os.path.join(arguments.output, 'step_1')
    spades_directory              = os.path.join(arguments.output, 'step_2')
    spades_transcripts            = os.path.join(spades_directory, 'transcripts.fasta')
    spades_transcripts_clear      = os.path.join(spades_directory, 'transcripts-clear.fasta')
    vnom_directory                = os.path.join(arguments.output, 'step_3')
    vnom_directory_candidates     = os.path.join(arguments.output, 'step_3', 'candidates')
    prodigal_directory            = os.path.join(arguments.output, 'step_4')
    prodigal_directory_corrected  = os.path.join(arguments.output, 'step_4', 'corrected')

    reads_1_raw  = arguments.reads[0]
    reads_2_raw  = arguments.reads[1]
    reads_1_trim = os.path.join(fastp_directory, 'reads_1.fastq')
    reads_2_trim = os.path.join(fastp_directory, 'reads_2.fastq')
    vnom_input   = os.path.join(vnom_directory, 'transcripts')
    vnom_output  = os.path.join(vnom_directory, 'transcripts_cir.fasta')
    
    # step_1 quality control

    os.system(f'mkdir -p {fastp_directory}')
    step_1_return_code = run_fastp(reads_1_raw, reads_2_raw, reads_1_trim, reads_2_trim, min_quality=arguments.min_qual)
    if step_1_return_code != 0:
        print('Error while read quality control')
        exit(1)

    # step_2: run assembly

    os.system(f'mkdir -p {spades_directory}')
    step_2_return_code = run_spades(
        reads_1_trim, 
        reads_2_trim, 
        arguments.threads, 
        spades_directory, 
        stranded_type=arguments.stranded_type
    )
    
    if step_2_return_code != 0:
        print('Error while assembling RNA sequences')
        exit(1)
    
    filter_and_rename_spades_transcripts(spades_transcripts, spades_transcripts_clear)
    os.system(f'cp {spades_transcripts_clear} {vnom_input}.fasta')
    
    # step_3: run viroid circRNA detection

    os.system(f'mkdir -p {vnom_directory}')
    os.system(f'mkdir -p {vnom_directory_candidates}')
    step_3_return_code = run_vnom(vnom_input, max_length=arguments.max_len)
    if step_3_return_code != 0:
        print('Error while identifying viroid-like sequences')
        exit(1)

    obelisks_candidates = split_vnom_candidates(vnom_output, vnom_directory_candidates, min_length=arguments.min_len, max_length=arguments.max_len)
    
    # step_4: run annotation: prodigal

    os.system(f'mkdir -p {prodigal_directory}')
    os.system(f'mkdir -p {prodigal_directory_corrected}')

    for obelisk_id, obelisk_candidate in enumerate(obelisks_candidates):
        if not os.path.isfile(obelisk_candidate):
            continue
        prodigal_output = os.path.join(prodigal_directory, os.path.basename(obelisk_candidate) + '.gff')
        step_4_return_code = run_prodigal(obelisk_candidate, prodigal_output)

        if step_4_return_code != 0:
            print('Error while identifying CDSs in the sequences')
            exit(1)
        try:
            obelisk_record = next(GFF.parse(open(prodigal_output)) )
            obelisk_record.seq = next(SeqIO.parse(obelisk_candidate, 'fasta')).seq
        except:
            continue
        obelisk_candidate_corrected_fasta = os.path.join(prodigal_directory_corrected, os.path.basename(obelisk_candidate))
        obelisk_candidate_corrected_rnafold = os.path.join(prodigal_directory_corrected, os.path.basename(obelisk_candidate)) + '.txt'
        obelisk_candidate_corrected_genbank = os.path.join(prodigal_directory_corrected, os.path.basename(obelisk_candidate) + '.gbk')           
        record = correct_contig(obelisk_record, obelisk_candidate_corrected_genbank)


        SeqIO.write([record], obelisk_candidate_corrected_fasta, 'fasta')
        SeqIO.write([record], obelisk_candidate_corrected_genbank, 'genbank')

        if record is None:
            continue

        sites = run_cmscan(obelisk_candidate_corrected_fasta, prodigal_directory, arguments.cm_directory)
        record = add_rfam_sites_to_record(record, sites)

        SeqIO.write([record], obelisk_candidate_corrected_fasta, 'fasta')
        SeqIO.write([record], obelisk_candidate_corrected_genbank, 'genbank')

        # step_5: run secondary structure analysis
        
        run_rnafold(obelisk_candidate_corrected_fasta, obelisk_candidate_corrected_rnafold)

        self_pairing_percent = compute_self_pairing_percent(obelisk_candidate_corrected_rnafold)
        if self_pairing_percent >= arguments.minimum_self_pairing_percent:
            os.system(f'cp {obelisk_candidate_corrected_fasta} {arguments.output}/obelisk_{obelisk_id+1}.fasta')
            os.system(f'cp {obelisk_candidate_corrected_genbank} {arguments.output}/obelisk_{obelisk_id+1}.gbk')
    
if __name__ == '__main__':
    main()