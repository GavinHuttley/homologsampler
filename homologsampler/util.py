import sqlalchemy as sql
from cogent3 import LoadTable
from ensembldb3 import Species
from ensembldb3.host import get_db_name

__author__ = "Gavin Huttley"
__copyright__ = "Copyright 2014, Gavin Huttley"
__credits__ = ["Gavin Huttley"]
__license__ = "BSD"
__version__ = "0.11"
__maintainer__ = "Gavin Huttley"
__email__ = "Gavin.Huttley@anu.edu.au"
__status__ = "Development"

def display_available_dbs(account, release=None):
    """displays the available Ensembl databases at the nominated host"""
    db_list = get_db_name(account=account, db_type='core', release=release)
    db_list += get_db_name(account=account, db_type='compara', release=release)
    rows = []
    for db_name in db_list:
        species_name = db_name.species
        if species_name:
            common_name = Species.get_common_name(db_name.species, level='ignore')
    
        if 'compara' in db_name.name:
            species_name = common_name = '-'
        rows.append([db_name.release, db_name.name, species_name, common_name])

    table = LoadTable(header=["Release", "Db Name", "Species", "Common Name"], rows=rows, space=2)
    table = table.sorted(["Release", "Db Name"])
    table.legend = "Values of 'None' indicate cogent does not have a value for that database name."
    return table

def species_names_from_csv(species):
    """returns species names"""
    species = [s.strip() for s in species.split(',')]
    return species

def missing_species_names(names):
    '''returns a Table of missing species names, or None'''
    missing = []
    for name in names:
        n = Species.get_species_name(name)
        if n == 'None':
            missing.append([name])
    
    if missing:
        result = LoadTable(header=["MISSING SPECIES"], rows=missing)
    else:
        result = None
    return result

def get_chrom_names(ref_species, compara):
    """returns the list of chromosome names"""
    genome_db = compara.ComparaDb.get_table("genome_db")
    dnafrag = compara.ComparaDb.get_table("dnafrag")
    joined = genome_db.join(dnafrag, onclause=genome_db.c.genome_db_id==dnafrag.c.genome_db_id)
    condition = sql.and_(dnafrag.c.coord_system_name=="chromosome",
                    genome_db.c.name==Species.get_ensembl_db_prefix(ref_species),
                    dnafrag.c.is_reference==1)
    query = sql.select([dnafrag.c.name], condition).select_from(joined)
    chroms = [r[0] for r in query.execute()]
    return chroms

def load_coord_names(infile_path):
    """loads chrom names, assumes separate name per file"""
    with open(infile_path) as infile:
        coord_names = [l.strip() for l in infile]
    return coord_names
