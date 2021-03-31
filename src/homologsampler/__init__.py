import gzip
import os
import sys
import warnings
from collections import Counter

import click
from cogent3 import (DNA, load_table, make_aligned_seqs, make_table,
                     make_unaligned_seqs)
from ensembldb3 import Compara, Genome, HostAccount, Species
from scitrack import CachingLogger

from homologsampler.util import (abspath, display_available_dbs,
                                 get_chrom_names, load_coord_names,
                                 missing_species_names, species_names_from_csv)

__author__ = "Gavin Huttley"
__copyright__ = "Copyright 2021-date, Gavin Huttley"
__credits__ = ["Gavin Huttley"]
__license__ = "BSD"
__version__ = "2021.04.01"
__maintainer__ = "Gavin Huttley"
__email__ = "Gavin.Huttley@anu.edu.au"
__status__ = "Development"

LOGGER = CachingLogger(create_dir=True)


def get_one2one_orthologs(
    compara, ref_genes, outpath, not_strict, force_overwrite, test
):
    """writes one-to-one orthologs of protein coding genes to outpath"""

    species = Counter(compara.species)
    written = 0
    records = []
    with click.progressbar(ref_genes, label="Finding 1to1 orthologs") as ids:
        for gene in ids:
            outfile_name = os.path.join(outpath, "%s.fa.gz" % gene)
            if os.path.exists(outfile_name) and not force_overwrite:
                written += 1
                continue

            syntenic = list(
                compara.get_related_genes(
                    stableid=gene, relationship="ortholog_one2one"
                )
            )

            if len(syntenic) != 1:
                continue

            syntenic = syntenic[0]

            if not not_strict and (
                syntenic is None or Counter(syntenic.get_species_set()) != species
            ):
                # skipping, not all species had a 1to1 ortholog for this gene
                continue

            seqs = []
            for m in syntenic.members:
                records.append([gene, m.stableid, m.location, m.description])
                name = Species.get_common_name(m.genome.species)
                cds = m.canonical_transcript.cds.trim_stop_codon(allow_partial=True)
                cds.name = name
                seqs.append([name, cds])

            seqs = make_unaligned_seqs(data=seqs)
            if test:
                print()
                print(gene)
                print(seqs.to_fasta())
            else:
                with gzip.open(outfile_name, "wt") as outfile:
                    outfile.write(seqs.to_fasta() + "\n")
                LOGGER.output_file(outfile_name)

            written += 1
    if test:
        msg = "Would have written %d files to %s" % (written, outpath)
    else:
        msg = "Wrote %d files to %s" % (written, outpath)

    click.echo(msg)

    if written > 0:
        metadata = make_table(
            header=["refid", "stableid", "location", "description"], rows=records
        )
        metadata.write(os.path.join(outpath, "metadata.tsv"))

    return


def get_latin_from_label(label):
    """returns latin name from the sequence label"""
    return label.split(":")[0]


def renamed_seqs(aln):
    """renames sequences to be just species common name"""
    new = []
    names = Counter()
    for seq in aln.seqs:
        latin = get_latin_from_label(seq.name)
        common = Species.get_common_name(latin)
        names[common] += 1
        seq.name = common
        new.append((seq.name, seq))

    if max(list(names.values())) > 1:
        # a species occures more than once
        return None

    return make_aligned_seqs(data=new, moltype=DNA, array_align=False)


def with_masked_features(aln, reverse=False):
    """returns an alignment with the tandem repeat sequences masked"""
    for name in aln.names:
        seq = aln.get_seq(name)
        remove = []
        for a in seq.annotations:
            if a.name not in ("trf", "cpg", "splice"):
                remove.append(a)
                break

        if remove:
            seq.detach_annotations(remove)

    if reverse:
        aln = aln.rc()

    aln = aln.with_masked_annotations(["repeat", "cpg"], mask_char="?")
    aln = aln.with_masked_annotations(["exon"], mask_char="?")
    return aln


def get_syntenic_alignments_introns(
    compara,
    ref_genes,
    outpath,
    method_clade_id,
    mask_features,
    outdir,
    force_overwrite,
    test,
):
    """writes Ensembl `method` syntenic alignments to ref_genes"""
    species = Counter(compara.species)
    common_names = list(map(Species.get_common_name, compara.species))
    filler = make_aligned_seqs(
        data=[(n, "N") for n in common_names], moltype=DNA, array_align=False
    )

    written = 0
    records = []
    with click.progressbar(ref_genes, label="Finding 1to1 intron orthologs") as ids:
        for gene_id in ids:
            valid_locations = True
            locations = {}
            gene = _get_gene_from_compara(compara, gene_id)
            if not gene:
                LOGGER.log_message("stableid '%s' not found" % gene_id)
                continue

            if gene.canonical_transcript.introns is None:
                LOGGER.log_message("stableid '%s' has no introns" % gene_id)
                continue

            outfile_name = os.path.join(outpath, "%s.fa.gz" % gene.stableid)
            if os.path.exists(outfile_name) and not force_overwrite:
                written += 1
                continue

            regions = list(
                compara.get_syntenic_regions(
                    region=gene.canonical_transcript,
                    method_clade_id=str(method_clade_id),
                )
            )
            alignments = []
            for index, region in enumerate(regions):
                if region is None:
                    msg = "stableid '%s' has no syntenic regions" % gene_id
                    LOGGER.log_message(msg)
                    continue

                try:
                    got = Counter(region.get_species_set())
                except (AttributeError, AssertionError):
                    got = None
                    # this is a PyCogent bug
                    error = sys.exc_info()
                    err_type = str(error[0]).split(".")[-1][:-2]
                    err_msg = str(error[1])
                    msg = "gene_stable_id=%s; err_type=%s; msg=%s" % (
                        gene.stableid,
                        err_type,
                        err_msg,
                    )
                    click.secho("ERROR:" + msg, fg="red")
                    LOGGER.log_message(msg, label="ERROR")
                    continue

                if got != species:
                    msg = [
                        "stableid '%s'" % gene_id,
                        "species set %s" % got,
                        "does not match expected %s" % species,
                    ]
                    LOGGER.log_message(" ".join(msg))
                    continue

                if mask_features:
                    aln = region.get_alignment(feature_types=["gene", "repeat", "cpg"])
                    aln = with_masked_features(aln, reverse=gene.location.strand == -1)
                else:
                    aln = region.get_alignment()

                if aln is None:
                    msg = "stableid '%s' has no syntenic alignment" % gene_id
                    LOGGER.log_message(msg)
                    continue

                aln = renamed_seqs(aln)
                if aln is not None:
                    alignments.append(aln)

                for m in region.members:
                    if m.location is None:
                        valid_locations = False
                        break

                    if m.genome.species not in locations:
                        union = m.location
                    elif m.genome.species in locations:
                        try:
                            union = locations[m.genome.species].union(m.location)
                        except AttributeError:
                            raise AttributeError("%s" % str([gene_id, m.genome]))

                    if union is None:
                        valid_locations = False
                        break

                    locations[m.genome.species] = union

            if not alignments:
                msg = "stableid '%s' has no alignments" % gene_id
                LOGGER.log_message(msg)
                continue

            if not valid_locations:
                msg = [
                    "stableid '%s' has" % gene_id,
                    "inconsistent location data for gene",
                    "based syntenic block %s" % locations,
                ]
                LOGGER.log_message(" ".join(msg), label="WARN")
                continue

            assert len(locations) == len(species), locations
            for sp, loc in locations.items():
                records.append([gene_id, loc])

            # we put a column of Ns between syntenic regions so that subsequent
            # sampling for tuple aligned columns does not construct artificial
            # motifs
            align = None
            for aln in alignments:
                if align is None:
                    align = aln
                    continue

                align += filler + aln

            if test:
                print(repr(align))
            else:
                with gzip.open(outfile_name, "wt") as outfile:
                    outfile.write(align.to_fasta())
                LOGGER.output_file(outfile_name)

            written += 1

    click.secho("Wrote %d files to %s" % (written, outpath), fg="green")
    if written > 0:
        metadata = make_table(header=["refid", "location"], rows=records)
        metadata.write(os.path.join(outpath, "metadata.tsv"))

    return


def display_ensembl_alignment_table(compara):
    """prints the method_species_link table and then exits"""
    compara.method_species_links.Legend = (
        "Assign the desired value from method_link_species_set_id to the"
        " method_clade_id argument"
    )
    print(compara.method_species_links)
    exit(0)


def _get_account(ensembl_account):
    """returns HostAccount or None"""
    try:
        acc = HostAccount(*ensembl_account.split())
    except (KeyError, AttributeError):
        warnings.warn(
            "ENSEMBL_ACCOUNT environment variable not set, "
            "defaulting to UK sever. Slow!!"
        )
        acc = None

    return acc


def _get_gene_from_compara(compara, stable_id):
    """returns gene instance from a compara db"""
    gene = None
    for sp in list(compara._genomes.values()):
        gene = sp.get_gene_by_stableid(stable_id)
        if gene:
            break
    return gene


def _get_ref_genes(ref_genome, chroms, limit, biotype="protein_coding"):
    """returns stable ID's for genes from reference genome"""
    limit = None if not limit else limit
    print("Sampling %s genes" % ref_genome)
    all_genes = ref_genome.get_genes_matching(biotype=biotype)
    ref_genes = []
    with click.progressbar(all_genes, label="Finding genes") as genes:
        for index, g in enumerate(genes):
            if limit is not None and index >= limit:
                break
            if chroms and g.location.coord_name not in chroms:
                continue

            ref_genes.append(g)
    return ref_genes


class Config(object):
    def __init__(self):
        super(Config, self).__init__()
        self.force_overwrite = False
        self.test = False


_ensembl_account = click.option(
    "--ensembl_account",
    envvar="ENSEMBL_ACCOUNT",
    help="shell variable with MySQL account "
    "details, e.g. export "
    "ENSEMBL_ACCOUNT='myhost.com jill jills_pass'",
)
_force_overwite = click.option(
    "-F", "--force_overwrite", is_flag=True, help="Overwrite existing files."
)
_test = click.option(
    "--test",
    is_flag=True,
    help="sets limit # queries to 2, " "does not write files, prints seqs and exits.",
)
_release = click.option("--release", help="Ensembl release.")
_species = click.option(
    "--species",
    required=True,
    callback=species_names_from_csv,
    help="Comma separated list of species names.",
)
_outdir = click.option(
    "--outdir",
    required=True,
    type=click.Path(resolve_path=False),
    help="Path to write files.",
)
_ref = click.option("--ref", default=None, help="Reference species.")
_ref_genes_file = click.option(
    "--ref_genes_file",
    default=None,
    type=click.Path(resolve_path=True, exists=True),
    help=".csv or .tsv file with a header containing a" " stableid column",
)
_coord_names = click.option(
    "--coord_names",
    default=None,
    type=click.Path(resolve_path=True),
    help="File containing chrom/coord names to " "restrict sampling to, one per line.",
)
_not_strict = click.option(
    "--not_strict",
    is_flag=True,
    help="Genes with an ortholog in any species are "
    "exported. Default is all species must have a "
    "ortholog.",
)
_introns = click.option(
    "--introns",
    is_flag=True,
    help="Sample syntenic alignments of introns, requires" " --method_clade_id.",
)
_method_clade_id = click.option(
    "--method_clade_id",
    help="The value of method_link_species_set_id "
    "required if sampling introns. Use "
    "show_align_methods command for options",
)
_mask_features = click.option(
    "--mask_features", is_flag=True, help="Intron masks repeats, exons, CpG islands."
)
_limit = click.option(
    "--limit", type=int, default=0, help="Limit to this number of genes."
)
_minlength = click.option(
    "--minlength", type=int, default=0, help="Minimum length allowed."
)
_logfile_name = click.option(
    "--logfile_name",
    default="one2one.log",
    help="Name for log file, written to outdir.",
)
_version = click.version_option(version=__version__)

_outpath = click.option(
    "--outpath", required=True, default="gene_metadata.tsv", help="Output file name."
)


@click.group()
@_version
def cli():
    pass


@cli.command()
@_ensembl_account
@_species
@_outpath
@_coord_names
@_release
@_limit
def dump_genes(ensembl_account, species, outpath, coord_names, release, limit):
    """Dump meta data table for genes from one species in release ENSEMBL_ACCOUNT
    and exits."""
    ensembl_account = _get_account(ensembl_account)
    if len(species) > 1:
        msg = "dump_genes handles single species only"
        click.secho(msg, fg="red")
        sys.exit(-1)

    missing_species = missing_species_names(species)
    if missing_species:
        msg = [
            "The following species names don't match an Ensembl record. "
            "Check spelling!",
            str(missing_species),
            "\nAvailable species are at this server are:",
            str(display_available_dbs(ensembl_account)),
        ]

        click.secho("\n".join(msg), fg="red")
        sys.exit(-1)

    if coord_names:
        chroms = load_coord_names(coord_names)
    else:
        chroms = None

    genome = Genome(species[0], release=release, account=ensembl_account)
    genes = _get_ref_genes(genome, chroms, limit)
    records = []
    for g in genes:
        records.append([g.stableid, g.biotype, g.location, g.description])

    if records:
        table = make_table(
            header=["stableid", "biotype", "location", "description"], rows=records
        )
        table.write(outpath)
        click.secho("Wrote %d genes to %s" % (table.shape[0], outpath), fg="green")
    else:
        click.secho("No genes matching criteria", fg="blue")


@cli.command()
@_ensembl_account
@_release
def show_available_species(ensembl_account, release):
    """shows available species and Ensembl release at ENSEMBL_ACCOUNT"""
    ensembl_account = _get_account(ensembl_account)
    available = display_available_dbs(ensembl_account, release)
    available.title = "Species available at: %s" % str(ensembl_account)
    print(available)
    sys.exit(0)


@cli.command()
@_ensembl_account
@_species
@_release
def show_align_methods(ensembl_account, species, release):
    """Shows the align methods in release ENSEMBL_ACCOUNT and exits."""
    ensembl_account = _get_account(ensembl_account)
    missing_species = missing_species_names(species)
    if missing_species:
        msg = [
            "The following species names don't match an Ensembl record. "
            "Check spelling!",
            str(missing_species),
            "\nAvailable species are at this server are:",
            str(display_available_dbs(ensembl_account)),
        ]

        click.secho("\n".join(msg), fg="red")
        sys.exit(-1)

    compara = Compara(species, release=release, account=ensembl_account)

    if show_align_methods:
        display_ensembl_alignment_table(compara)


@cli.command()
@_ensembl_account
@_species
@_release
@_outdir
@_ref
@_ref_genes_file
@_coord_names
@_not_strict
@_introns
@_method_clade_id
@_mask_features
@_logfile_name
@_limit
@_force_overwite
@_test
def one2one(
    ensembl_account,
    species,
    release,
    outdir,
    ref,
    ref_genes_file,
    coord_names,
    not_strict,
    introns,
    method_clade_id,
    mask_features,
    logfile_name,
    limit,
    force_overwrite,
    test,
):
    """Command line tool for sampling homologous sequences from Ensembl."""
    outdir = abspath(outdir)
    if not any([ref, ref_genes_file]):
        # just the command name, indicate they need to display help
        click.secho("Missing 'ref' and 'ref_genes_file'")
        ctx = click.get_current_context()
        msg = "%s\n\n--help to see all options\n" % ctx.get_usage()
        click.echo(msg)
        exit(-1)

    ensembl_account = _get_account(ensembl_account)
    args = locals()
    args["ensembl_account"] = str(ensembl_account)
    LOGGER.log_message(str(args), label="params")

    if test and limit == 0:
        limit = 2
    else:
        limit = limit or None

    if (introns and not method_clade_id) or (mask_features and not introns):
        msg = [
            "Must specify the introns and method_clade_id in order to",
            "export introns. Use show_align_methods to see the options",
        ]
        click.secho("\n".join(msg), fg="red")
        exit(-1)

    species_missing = missing_species_names(species)
    if species_missing:
        msg = [
            "The following species names don't match an Ensembl record."
            " Check spelling!",
            str(species_missing),
            "\nAvailable species are at this server are:",
            str(display_available_dbs(ensembl_account)),
        ]

        click.secho("\n".join(msg), fg="red")
        exit(-1)

    if ref:
        ref = ref.lower()

    if ref and ref not in species:
        print("The reference species not in species names")
        exit(-1)

    compara = Compara(species, release=release, account=ensembl_account)
    runlog_path = os.path.join(outdir, logfile_name)

    if os.path.exists(runlog_path) and not force_overwrite:
        msg = [
            "Log file (%s) already exists!" % runlog_path,
            "Use force_overwrite or provide logfile_name",
        ]
        click.secho("\n".join(msg), fg="red")
        exit(-1)

    if not test:
        LOGGER.log_file_path = runlog_path

    chroms = None
    if coord_names:
        chroms = load_coord_names(coord_names)
        LOGGER.input_file(coord_names)
    elif coord_names and ref:
        chroms = get_chrom_names(ref, compara)

    if not os.path.exists(outdir) and not test:
        os.makedirs(outdir)
        print("Created", outdir)

    if ref and not ref_genes_file:
        ref_genome = Genome(ref, release=release, account=ensembl_account)
        ref_genes = [g.stableid for g in _get_ref_genes(ref_genome, chroms, limit)]
    else:
        if not (ref_genes_file.endswith(".csv") or ref_genes_file.endswith(".tsv")):
            msg = (
                "ref_genes_file must be either a comma/tab "
                "delimted with the corresponding suffix (.csv/.tsv)"
            )
            click.secho(msg, fg="red")
            exit(-1)

        ref_genes = load_table(ref_genes_file)
        if "stableid" not in ref_genes.header:
            msg = "ref_genes_file does not have a 'stableid' column header"
            click.secho(msg, fg="red")
            exit(-1)

        ref_genes = ref_genes.tolist("stableid")

    if limit:
        ref_genes = ref_genes[:limit]

    if not introns:
        print("Getting orthologs %d genes" % len(ref_genes))
        get_one2one_orthologs(
            compara, ref_genes, outdir, not_strict, force_overwrite, test
        )
    else:
        print("Getting orthologous introns for %d genes" % len(ref_genes))
        get_syntenic_alignments_introns(
            compara,
            ref_genes,
            outdir,
            method_clade_id,
            mask_features,
            outdir,
            force_overwrite,
            test,
        )


@cli.command()
@_ensembl_account
@_species
@_outdir
@_coord_names
@_release
@_minlength
@_limit
def intergenic_aligns(
    ensembl_account, species, outdir, coord_names, release, minlength, limit
):
    """Exports intergenic alignments"""
    outdir = abspath(outdir)
    ensembl_account = _get_account(ensembl_account)
    args = locals()
    args["ensembl_account"] = str(ensembl_account)
    LOGGER.log_message(str(args), label="params")

    if coord_names:
        chroms = load_coord_names(coord_names)
    else:
        chroms = None


if __name__ == "__main__":
    cli()
