##############
HomologSampler
##############

This is a command line tool for sampling related sequences from Ensembl. It requires cogent3, numpy, SQLAlchemy, PyMysql, click and scitrack. The latter basically logs commands, file inputs and outputs, to assist with reproducible research.

HomologSampler has one command line tool ``homolog_sampler``. At present, this tool provides capabilities to support sampling one-to-one orthologs from protein coding genes stored in an Ensembl_ MySQl database. It can either write out the protein coding sequences from the canonical CDS, or it can write out the Ensembl multiple sequence alignment of the entire gene with annotated features masked.

Increasing the number of biotypes and the homology relationships will be done at a later date.

************
Installation
************

First install `ensembldb3 <https://github.com/cogent3/ensembldb3>`_, then do::

    $ pip install git+http://github.com/cogent3/homologsampler.git@master#egg=homologsampler

**************
Main help page
**************

::

    $ homolog_sampler 
    Usage: homolog_sampler [OPTIONS] COMMAND [ARGS]...

    Options:
      --ensembl_account TEXT  shell variable with MySQL account details, e.g.
                              export ENSEMBL_ACCOUNT='myhost.com jill jills_pass'
      -F, --force_overwrite   Overwrite existing files.
      --test INTEGER          limit to # queries (default is 2), does not write
                              files, prints seqs and exits.
      --version               Show the version and exit.
      --help                  Show this message and exit.

    Commands:
      one2one                 Command line tool for sampling homologous...
      show_align_methods      Shows the align methods in release...
      show_available_species  shows available species and Ensembl release...

To show available species
=========================

::

    $ homolog_sampler show_available_species
    Species available at: username:passwd@your.mysql.server
    =================================================================================================
    release                                   Db Name                     Species         Common Name
    -------------------------------------------------------------------------------------------------
         20              ashbya_gossypii_core_20_73_1                        None                None
         20         aspergillus_clavatus_core_20_73_1        Aspergillus clavatus          A.clavatus
         20           aspergillus_flavus_core_20_73_1          Aspergillus flavus            A.flavus
         20        aspergillus_fumigatus_core_20_73_2       Aspergillus fumigatus         A.fumigatus...

To sample orthologs CDS
=======================

::

    $ homolog_sampler one2one --release 81 --ref human --species human,mouse,opossum --outdir sampled_cds

This command will write CDSs sequences to the directory ``sampled_cds`` as gzip compressed fasta files with the file prefix as the human Ensembl gene stable identifier (e.g. ``ENSG00000012048.fa.gz``).

To sample syntenic introns
==========================

We first need to know the Ensembl alignment method identifier. We get this as follows ::

    $ homolog_sampler show_align_methods --species human,mouse,opossum --release=81
    Align Methods/Clades
    ======================================================================================================
    method_link_species_set_id  method_link_id  species_set_id  align_method                   align_clade
    ------------------------------------------------------------------------------------------------------
                           788              10           36176         PECAN  23 amniota vertebrates Pecan
    ------------------------------------------------------------------------------------------------------
    Assign the desired value from method_link_species_set_id to the method_clade_id argument

We then use the ``one2one`` subcommand ::

    $ homolog_sampler one2one --release 81 --ref human --species human,mouse,opossum --outdir sampled_intron --introns --method_clade_id 788

.. _pip: https://pip.pypa.io/en/stable/installing/
.. _Ensembl: http://www.ensembl.org