import cgi
from collections import Counter
import json
from math import log
import os
from os import path
import pickle
import pprint
import re

from external import identifier_renamer
from pipeline_util import ensure_folder_exists, make_hashable

use_original_line_equality_metric = False

CORRECT_OUTPUT = {
    "dotProduct([-22, -54, 20, 23, 76, 0], [48, 62, -4, 89, -41, 15])": -5553, 
    "dotProduct([-45], [-60])": 2700, 
    "dotProduct([-62, 4, 73, -46, 79, -56], [77, -80, 3, 99, 59, 7])": -5160, 
    "dotProduct([-7, 96, -5, -45, -50, 5, -98, -16, -58], [88, -79, -47, 4, -19, -14, -47, -75, 35])": -3489, 
    "dotProduct([-90, -29, 36, -74, -24, 10, -16, 16, -28], [68, 39, -5, 7, 67, 91, 48, -60, -67])": -8499, 
    "dotProduct([31, 98, -78, -50, 55, -4], [-94, -23, -56, 31, 77, -84])": 2221, 
    "dotProduct([4, 69, -97], [-91, -71, -93])": 3758, 
    "dotProduct([68, 33, 56, 20, 4], [18, 93, -15, -57, -82])": 1985, 
    "dotProduct([69, 57, -64, -4, -5, -32, 30, 33], [-13, -16, -73, 26, -11, 98, 100, -8])": 2414, 
    "dotProduct([72, 18, 18, -57, -91, 61], [37, 8, 11, 30, 2, -64])": -2790
}
# CORRECT_OUTPUT = {
#     "dotProduct([1, 2, 3], [4, 5, 6])": 32
# }


###############################################################################
## Helper functions
###############################################################################
def add_to_setlist(elem,setlist):
    """Maintains a list of unique items in the order they were added"""

    if setlist==[]:
        setlist.append(elem)
    else:
        for listelem in setlist:
            if elem == listelem:
                return
        setlist.append(elem)


###############################################################################
## Classes
###############################################################################
class Solution(object):
    """Information about a single solution."""

    def __init__(self, solnum, testcase_to_trace):
        self.solnum = solnum
        # a dictionary mapping a testcase string to a trace
        self.testcase_to_trace = testcase_to_trace
        self.local_vars = []
        self.abstract_vars = []
        # a list of (line object, local names, indent) tuples
        self.lines = []
        # a list of line objects
        self.canonical_lines = []

        self.var_obj_to_templates = {}
        self.correct = None

    def getDict(self):
        return self.__dict__

    def __str__(self):
        return "Solution(" + str(self.solnum) + ")"
    __repr__ = __str__

class VariableInstance(object):
    """A single variable within a solution."""

    def __init__(self, sequence, solnum, local_name):
        self.sequence = sequence
        self.solnum = solnum
        self.local_name = local_name
        self.abstract_var = None
        self.rename_to = None

        self.templates = set()

    def __repr__(self):
        return "Variable(" + self.local_name + ") in solution " + str(self.solnum)

    def __str__(self):
        s = """
Local name: %s
Solution: %s
Sequence: %s
""" % (self.local_name, self.solnum, str(self.sequence))
        if self.abstract_var:
            s += "Belongs to: " + AbstractVariable.__repr__(self.abstract_var)
        return s

class AbstractVariable(object):
    """A canonical variable as characterized by its sequence of values."""

    def __init__(self, sequence):
        # Sequence of values taken on by this variable
        self.sequence = sequence
        # solnum -> local name of this variable in that solution
        self.solutions = {}
        # Counter for keeping track of most common names
        self.name_ctr = Counter()
        self.canon_name = None
        self.is_unique = None

        self.templates = set()

    def should_contain(self, inst):
        """
        Whether a particular VariableInstance is an example of this abstract
        variable.

        inst: an instance of VariableInstance
        returns: boolean, True if inst should be added to self, False otherewise.
        """
        assert isinstance(inst, VariableInstance)
        return self.sequence == inst.sequence

    def add_instance(self, inst):
        """
        Add a VariableInstance to this abstract variable.

        inst: an instance of VariableInstance. Must not be associated with
              another AbstractVariable.
        """
        assert isinstance(inst, VariableInstance)
        assert inst.abstract_var == None

        # Update internal data structures
        self.solutions[inst.solnum] = inst.local_name
        self.name_ctr[inst.local_name] += 1
        if self.is_unique==None:
            self.is_unique = True
        elif self.is_unique:
            self.is_unique = False
        # Link the VariableInstance to this AbstractVariable
        inst.abstract_var = self

    def most_common_name(self):
        """
        Get the most common name for this abstract variable across all solutions.

        returns: string, most common name
        """

        name, count = self.name_ctr.most_common(1)[0]
        return name

    def print_solutions(self):
        """Pretty print the solutions containing this abstract variable."""
        pprint.pprint(self.solutions)

    def print_names(self):
        """Pretty print the local names given to this abstract variable."""
        pprint.pprint(self.name_ctr)

    def __eq__(self, other):
        """Two AbstractVariables are equal if they have the same sequence."""
        assert isinstance(other, AbstractVariable)
        return self.sequence == other.sequence

    def __hash__(self):
        return hash(make_hashable(self.sequence))

    def __repr__(self):
        if self.canon_name:
            inside = str(self.canon_name) + " " + str(self.sequence)
        else:
            inside = str(self.sequence)
        return "AbstractVariable(" + inside + ")"

    __str__ = __repr__

class Line(object):
    """A line of code, without indent recorded, with blanks for variables, and
    the corresponding abstract variables to fill the blanks."""

    def __init__(self, template, abstract_variables, line_values):
        self.template = template
        self.abstract_variables = abstract_variables
        # dictionary mapping testcase strings to sequences of values
        self.line_values = line_values

    def __hash__(self):
        if use_original_line_equality_metric:
            return hash((make_hashable(self.abstract_variables),self.template))
        return hash((make_hashable(self.line_values),self.template))

    def __eq__(self, other):
        """Old definition: Two Lines are equal if they have the same template and
        abstract variables. New definition: two Lines are equal if they have the
        same template and line values"""
        assert isinstance(other, Line)
        if use_original_line_equality_metric:
            return self.abstract_variables == other.abstract_variables and self.template == other.template
        return self.line_values == other.line_values and self.template == other.template

    def getDict(self):
        return self.__dict__

    def render(self):
        # Replace all the blanks with '{}' so we can use built-in string formatting
        # to fill in the blanks with the list of ordered names
        return self.template.replace('___', '{}').format(*self.abstract_variables) #todo: print cannon name .canon_name

    def __str__(self):
        return self.template + " ||| " + str(self.line_values) #+ " ||| " + line_values_formatted + "\n" # + " ||| " + str(self.local_names) + "\n"
    __repr__ = __str__

class Stack(object):
    """A group of Solutions that are considered equivalent."""
    def __init__(self):
        self.representative = None
        self.members = []
        self.count = 0

        self.var_obj_to_templates = {}

    def should_contain(self, sol):
        """
        Whether a particular solution belongs in this stack.

        sol: an instance of Solution
        returns: boolean, True if sol belongs in this stack, False otherwise
        """
        assert isinstance(sol, Solution)
        if self.representative == None:
            return True

        # This captures having the same output on all test cases, but only
        # works if the two solutions were run on the same set of tests.
        same_output = self.representative.output == sol.output

        # Use Counters instead of sets so that multiple lines with the same
        # template and values do not get collapsed into one in a single
        # solution. For example, two variables both instantiated to 0 will
        # both have the form ___=0, and the information that there were two
        # such lines should not be lost.
        lines_match = Counter(self.representative.canonical_lines) == Counter(sol.canonical_lines)
        return lines_match and same_output

    def add_solution(self, sol):
        """
        Add a solution to this stack.
        """
        assert isinstance(sol, Solution)
        if self.representative == None:
            self.representative = sol
        self.members.append(sol.solnum)
        self.count += 1

        for avar in sol.var_obj_to_templates:
            if avar in self.var_obj_to_templates:
                self.var_obj_to_templates[avar] |= sol.var_obj_to_templates[avar]
            else:
                self.var_obj_to_templates[avar] = sol.var_obj_to_templates[avar]


###############################################################################
## Load preprocessed data
###############################################################################
def populate_from_pickles(all_solutions, pickleSrc):
    """
    Load program traces, args and return variables from pickle files as
    created by the pipeline preprocessor. Create a Solution instance for
    each pickle file and add them to all_solutions.

    all_solutions: list to add solutions to
    pickleSrc: string, path to directory containing pickle files
    formattedSrc: string, path to directory containing formatted code, e.g.
                  as HTML
    formattedExtn: string, extension of files in the formattedSrc directory

    mutates all_solutions
    """

    print "Loading data"
    for filename in os.listdir(pickleSrc):
        solnum = filename.split('.')[0]
        # print solnum

        with open(path.join(pickleSrc, filename), 'r') as f:
            unpickled = pickle.load(f)

        testcases = unpickled['testcases']
        traces = unpickled['traces']

        testcase_to_trace = {}
        for i in range(len(testcases)):
            testcase_to_trace[testcases[i]] = traces[i]

        sol = Solution(solnum, testcase_to_trace)

        all_solutions.append(sol)

###############################################################################
## Abstract variable collection
###############################################################################
def add_to_abstracts(var, all_abstracts):
    """
    Add var to the AbstractVariable it belongs in, or create a new one if there
    is not yet an appropriate AbstractVariable.

    var: an instance of VariableInstance
    all_abstracts: list of existing AbstractVariable instances

    mutates all_abstracts and var
    """

    for abstract in all_abstracts:
        if abstract.should_contain(var):
            abstract.add_instance(var)
            break
    else:
        new_abstract = AbstractVariable(var.sequence)
        new_abstract.add_instance(var)
        all_abstracts.append(new_abstract)

def find_canon_names(all_abstracts):
    """
    Assign canon names to all AbstractVariables by appending a modifier to
    the most common name if it collides with another name, or appending a
    double underscore if a variable is unique.

    all_abstracts: list of AbstractVariable instances

    mutates the elements of all_abstracts
    """

    # name -> (count, AbstractVariable)
    name_dict = {}
    uniques = []

    # Create a map from names to a list of (number of solutions using
    # that name, associated AbstractVariable instance) pairs
    for abstract in all_abstracts:
        if abstract.is_unique:
            uniques.append(abstract)
            continue
        name = abstract.most_common_name()
        count = len(abstract.solutions)
        if name not in name_dict:
            name_dict[name] = [(count, abstract)]
        else:
            name_dict[name].append((count, abstract))

    # For each name, assign modifiers if necessary in order of popularity
    for name in name_dict:
        # Sorting tuples uses the first element by default, no need to specify
        name_dict[name].sort(reverse=True)
        for i in range(len(name_dict[name])):
            count, abstract = name_dict[name][i]
            append = '' if i == 0 else '___' + str(i + 1)
            abstract.canon_name = name + append

    # Unique variables just get double underscores if they clash
    for unique in uniques:
        name = unique.most_common_name()
        if name in name_dict:
            unique.canon_name = name + '__'
        else:
            unique.canon_name = name

def find_template_info_scores(abstracts):
    counts = Counter()
    for avar in abstracts:
        counts.update(avar.templates)
    total = float(sum(counts.values()))

    # log2(1/p)
    scores = { template: log(total/count, 2) for template, count in counts.iteritems() }

    # Set a threshold that will separate templates that appear once from those
    # that appear more than once. The difference in entropy between a template
    # that appears once and one that appears twice is always 1 because of how
    # logs work, so just add 0.5 to separate nicely.
    threshold = log(total/2.0, 2) + 0.5
    return (scores, threshold)

###############################################################################
## Variable sequence extraction
###############################################################################
def extract_single_sequence(column):
    """
    Collapse a trace of variable values over time into a single sequence.

    column: list of (step, value) pairs
    returns: list of values
    """

    valueSequence = []
    for elem in column:
        val = elem[1]
        if val != 'myNaN' and val != None:

            if valueSequence == []:
                valueSequence.append(val)
            else:
                lastval = valueSequence[-1]
                if val != lastval:
                    valueSequence.append(val)
    return valueSequence

class ExtractionException(Exception):
    """No __return__ value in a solution trace."""

def extract_sequences_single_sol(sol, correct_abstracts, correct_output):
    """
    For each local variable in a single solution, extract its sequence of
    values, create a VariableInstance, and assign that VariableInstance to
    an AbstractVariable.

    sol: instance of Solution
    correct_abstracts: list of AbstractVariable instances. Can be empty.
    raises ExtractionException if there is no __return__ value in the
           solution trace

    mutates sol and correct_abstracts
    """

    output = {}
    sequences = {}
    for (testcase, trace) in sol.testcase_to_trace.iteritems():
        if '__return__' not in trace:
            raise ExtractionException('Solution did not run to completion')

        # The second-to-last step seems to always have the return value.
        # Steps in the trace are of the form (step, value), so take just
        # the value
        output[testcase] = trace['__return__'][-2][1]

        for localVarName, localVarData in trace.iteritems():
            if localVarName.startswith('__'):
                continue
            sequence = extract_single_sequence(localVarData)
            if (len(sequence) == 1 and
                type(sequence[0]) is str and
                sequence[0].startswith('__')):
                # Just a function definition
                continue
            if localVarName not in sequences:
                sequences[localVarName] = {}
            sequences[localVarName][testcase] = sequence

    sol.output = output
    sol.correct = (output == correct_output)

    for localVarName in sequences:
        # Create a new VariableInstance, add it to the solution's local vars,
        # assign it to an abstract variable, and add that to the solution's
        # abstract vars.
        var = VariableInstance(sequences[localVarName], sol.solnum, localVarName)
        sol.local_vars.append(var)

        if sol.correct:
            add_to_abstracts(var, correct_abstracts)
            sol.abstract_vars.append(var.abstract_var)
            var_to_map = var.abstract_var
        else:
            var_to_map = var

        if var_to_map not in sol.var_obj_to_templates:
            sol.var_obj_to_templates[var_to_map] = set()

def extract_and_collect_var_seqs(all_solutions,
                                 correct_solutions,
                                 incorrect_solutions,
                                 correct_abstracts):
    """
    Extract and collect variable information from all solutions.

    all_solutions: list of Solution instances
    incorrect_solutions: list for Solution instances that are incorrect and
        so have not had variables collected yet
    all_abstracts: list for AbstractVariable instances from correct solutions
    returns: list, solution numbers skipped

    mutates all_abstracts and elements of all_solutions
    """
    skipped = []
    for sol in all_solutions[:]:
        try:
            print "Collecting variables in", sol.solnum
            extract_sequences_single_sol(sol, correct_abstracts, CORRECT_OUTPUT)
            if sol.correct:
                correct_solutions.append(sol)
            else:
                incorrect_solutions.append(sol)
        except ExtractionException:
            # Since we are iterating through a copy, this will not cause problems
            all_solutions.remove(sol)
            skipped.append(sol.solnum)

    return skipped

###############################################################################
## Line computation functions
###############################################################################
def extract_var_values_at_line(line_number, local_name, trace):
    """
    Get the values of a particular variable on a single line over time.

    line_number: the line number we want values for
    local_name: the name of the variable we want values of
    trace: the trace to extract info from

    returns: a list of values representing the sequence of values of the
        given variable on a particular line
    """
    values = []
    # All the steps in the trace where the line being executed is the
    # line we care about
    relevant_steps = [step for (step, line_no) in trace['__lineNo__'] if line_no == line_number]

    for relevant_step in relevant_steps:
        # For each step in the trace, if we care about that step, pick
        # out the value of the variable we are examining
        try:
            for (step, val) in trace[local_name]:
                if step == relevant_step:
                    values.append(val)
                    break
        except KeyError:
            return "not_initialized"

    return values

def compute_lines(sol, tidy_path, all_lines):
    """
    Computes line objects for the solution, adds them to sol object and the
    all_lines setlist

    Mutates sol, all_lines
    """
    with open(tidy_path, 'U') as f:
        renamed_src = f.read()

    # This code renames all variables as placeholders, and saves a mapping
    # from placeholder to (original name, abstract variable object)
    mappings = {}
    ctr = 0
    for lvar in sol.local_vars:
        placeholder = '___' + str(ctr) + '___'
        try:
            renamed_src = identifier_renamer.rename_identifier(
                renamed_src, lvar.local_name, placeholder)
        except:
            raise RenamerException('Failed to rename ' + str(sol.solnum))

        ctr += 1

        var_to_map = lvar.abstract_var if sol.correct else lvar
        mappings[placeholder] = (lvar.local_name, var_to_map)

    # This code breaks solutions down into line objects
    # renamed_src consists of the solution with variables replaced with
    # numbered blanks.
    raw_lines = renamed_src.split('\n')
    for (line_no, raw_line) in enumerate(raw_lines, start=1):
        stripped_line = raw_line.strip()

        # Ignore empty lines
        if stripped_line == '':
            continue
        indent = len(raw_line) - len(stripped_line)

        blanks = re.findall(r'___\d___', stripped_line)
        if len(blanks) > 0:
            # Grab a list of (local name, abstract_var) pairs in the order
            # they appear and transform it into two ordered lists of local
            # names and abstract variable objects
            local_names, variable_objects = zip(*[mappings[blank] for blank in blanks])
        else:
            local_names = ()
            variable_objects = ()

        # The template is the raw line with numbered blanks replaced with
        # generic blanks
        template = re.sub(r'___\d___', '___', stripped_line)

        # line_values is a list of dictionaries, one per blank
        # Each dictionary maps from a testcase to a sequence of values
        line_values = []
        for lname in local_names:
            values = {}
            for (testcase, trace) in sol.testcase_to_trace.iteritems():
                values[testcase] = extract_var_values_at_line(line_no, lname, trace)
            line_values.append(values)
        
        line_object = Line(template, variable_objects, line_values)
        this_line_in_solution = (line_object, local_names, indent)
        
        sol.lines.append(this_line_in_solution)
        sol.canonical_lines.append(line_object)

        for var_obj in set(variable_objects):
            indices = tuple(i for (i, v) in enumerate(variable_objects) if v==var_obj)
            # sol.var_obj_to_templates[var_obj].add((template, indices))
            var_obj.templates.add((template, indices))

        add_to_setlist(line_object, all_lines)

def compute_all_lines(all_solutions, folderOfData, all_lines):
    skipped = []
    for sol in all_solutions:
        tidy_path = path.join(folderOfData, 'tidyData', sol.solnum + '.py')
        try:
            print "Computing lines for", sol.solnum
            compute_lines(sol, tidy_path,all_lines)
            # print 'length of lines ',len(all_lines)
        except RenamerException:
            skipped.append(sol.solnum)

    return skipped

###############################################################################
## Rewrite solutions
###############################################################################
def fix_name_clashes(sol):
    """
    Fix the problem with multiple copies of a single AbstractVariable within
    a single solution.

    sol: instance of Solution
    """

    if len(sol.abstract_vars) == len(set(sol.abstract_vars)):
        return
    assert len(sol.abstract_vars) > len(set(sol.abstract_vars))
    print 'Fixing clash in', sol.solnum

    # Multiple instances of a single abstract variable
    for var in sol.abstract_vars:
        indices = [i for i, v in enumerate(sol.abstract_vars) if v == var]
        if len(indices) == 1:
            continue
        for ind in indices:
            abs_var = sol.abstract_vars[ind]
            local_var = sol.local_vars[ind]
            if not abs_var.canon_name == local_var.local_name:
                # If canon and local names are both i, don't rename to i_i__
                new_name = abs_var.canon_name + '_' + local_var.local_name + '__'
                local_var.rename_to = new_name

class RenamerException(Exception):
    """A problem occurred while calling identifier_renamer."""

def rewrite_source(sol, tidy_path, canon_path):
    """
    Rename local variables within a single solution to their canon equivalents,
    or a modified version if there is a clash. Also stores the canonical python
    code in the Solution.

    sol: instance of Solution
    tidy_path: string, path to directory containing tidied source for sol
    canon_path: string, path to directory to write the canonicalized source to
    raises RenamerException if a problem occurs when renaming

    mutates sol
    """

    with open(tidy_path, 'U') as f:
        renamed_src = f.read()

    extra_token = '_temp'
    # Two passes to avoid conflicts between new names and old names
    # TODO: can this be abstracted? It's bothering me :(
    # First pass: local to <canon>_temp
    for lvar in sol.local_vars:
        if lvar.rename_to:
            shared_name = lvar.rename_to
        else:
            shared_name = lvar.abstract_var.canon_name

        try:
            renamed_src = identifier_renamer.rename_identifier(
                renamed_src, lvar.local_name, shared_name + extra_token)
        except:
            # Who knows what kind of exception this raises? Raise our own
            raise RenamerException('Failed to rename ' + str(sol.solnum))

    # Second pass: <canon>_temp to <canon>
    for lvar in sol.local_vars:
        if lvar.rename_to:
            shared_name = lvar.rename_to
        else:
            shared_name = lvar.abstract_var.canon_name

        try:
            renamed_src = identifier_renamer.rename_identifier(
                renamed_src, shared_name + extra_token, shared_name)
        except:
            # Who knows what kind of exception this raises? Raise our own
            raise RenamerException('Failed to rename ' + str(sol.solnum))

    with open(canon_path, 'w') as f:
        f.write(renamed_src)

def rewrite_all_solutions(all_solutions, folderOfData):
    """
    Rename variables across all solutions, write out the canonicalized code,
    and keep track of phrases.

    all_solutions: list of Solution instances
    folderOfData: base directory containing data and output folders
    returns: list, solution numbers skipped

    mutates elements of all_solutions
    """
    skipped = []

    canon_folder = path.join(folderOfData, 'tidyDataCanonicalized')
    ensure_folder_exists(canon_folder)
    for sol in all_solutions:
        fix_name_clashes(sol)

        tidy_path = path.join(folderOfData, 'tidyData', sol.solnum + '.py')
        canon_path = path.join(canon_folder, sol.solnum + '.py')
        try:
            print "Rewriting", sol.solnum
            rewrite_source(sol, tidy_path, canon_path)
        except RenamerException:
            skipped.append(sol.solnum)

    return skipped


###############################################################################
## Create stacks
###############################################################################
def stack_solutions(all_solutions, all_stacks):
    """
    Collect solutions into stacks.

    all_solutions: list of Solution instances
    all_stacks: list of existing Stacks

    mutates all_stacks
    """
    for sol in all_solutions:
        print "Stacking", sol.solnum
        for stack in all_stacks:
            if stack.should_contain(sol):
                stack.add_solution(sol)
                break
        else:
            new_stack = Stack()
            new_stack.add_solution(sol)
            all_stacks.append(new_stack)

###############################################################################
## do things with templates
###############################################################################
def template_sets_close_enough(set1, set2):
    in1not2 = set1 - set2
    in2not1 = set2 - set1
    return max(len(in1not2), len(in2not1)) == 1

def find_voting_stacks(correct_stacks, incorrect_solutions):
    correct_template_sets = [
        set(l.template for l in stack.representative.canonical_lines) for stack in correct_stacks
    ]
    for wrong_sol in incorrect_solutions:
        bad_template_set = set(l.template for l in wrong_sol.canonical_lines)
        indices = []
        for i, correct_set in enumerate(correct_template_sets):
            if template_sets_close_enough(bad_template_set, correct_set):
                indices.append(i)

        voting_stacks = [correct_stacks[i] for i in indices]
        wrong_sol.voting_stacks = voting_stacks

def find_matching_var(var_to_match, correct_abstracts, scores, threshold):
    # print "\n\nMatching for variable:", var_to_match.local_name
    # pprint.pprint(list(var_to_match.templates), indent=2)

    # print "trying to match:",var_to_match.local_name
    # best_shared = 0
    best_avar = None
    best_info_content = 0
    for avar in correct_abstracts:
        if avar.should_contain(var_to_match):
            avar.add_instance(var_to_match)
            return ('values_match', None)

        # print "\navar:", avar.canon_name
        # pprint.pprint(list(avar.templates), indent=2)

        diff = var_to_match.templates - avar.templates
        shared = var_to_match.templates & avar.templates
        # Since every template in correct abstract variables is in scores
        # and we are only looking up the score of templates that are shared
        # with correct abstract variables, we will never get key errors
        match_info_content = sum(scores[t] for t in shared)

        if match_info_content > threshold:
            if len(diff) == 0:
                # print "Matches with:", avar
                var_to_match.maps_to = avar
                return ('templates_match_perfectly', match_info_content)
            elif match_info_content > best_info_content:
                best_info_content = match_info_content
                best_avar = avar

    if best_avar is not None:
        var_to_match.maps_to = best_avar
        return ('templates_differ', best_info_content)
    else:
        return ('no_match', None)

def render_template_indices((template, indices), fill_in):
    buildme = []
    last_end = 0
    for i, match in enumerate(re.finditer('___', template)):
        buildme.append(template[last_end:match.start()])
        if i in indices:
            buildme.append(fill_in)
        else:
            buildme.append('___')
        last_end = match.end()
    buildme.append(template[last_end:])
    return ''.join(buildme)

def find_all_matching_vars(incorrect_solutions, correct_abstracts):
    scores, threshold = find_template_info_scores(correct_abstracts)
    total_num_vars = 0
    num_perfect = 0
    num_unmatched = 0
    output = []
    for sol in incorrect_solutions:
        for lvar in sol.local_vars:
            (match_type, info_content) = find_matching_var(
                lvar, correct_abstracts, scores, threshold)

            result = {
                'solution': sol.solnum,
                'original': [render_template_indices(t, lvar.local_name) for t in lvar.templates],
                'match_type': match_type
            }
            total_num_vars += 1
            if match_type == 'values_match':
                avar = lvar.abstract_var
                num_perfect += 1
                # continue
            elif match_type == 'no_match':
                output.append(result)
                num_unmatched += 1
                continue
            else:
                avar = lvar.maps_to
                result['info_content'] = info_content
            result['maps_to'] = [render_template_indices(t, avar.canon_name) for t in avar.templates],
            result['values_of_match'] = avar.sequence

            output.append(result)
    print "Total number of variables:", total_num_vars
    print "Number of perfect variables:", num_perfect
    print "Number of unmatched variables:",num_unmatched
    return output


###############################################################################
## Populate solutions, phrases, variables
###############################################################################
def create_output(all_stacks, solutions, phrases, variables, avar_template_info):
    """
    Make dictionaries in the expected output format by collecting
    info from the Stacks.

    all_stacks: list of Stack instances
    solutions, phrases, variables: lists to add results to

    mutates solutions, phrases, and variables
    """

    for stack in all_stacks:
        solution = {}
        solution['phraseIDs'] = set()
        solution['variableIDs'] = set()
        solution['lines'] = []
        rep = stack.representative
        for i in range(len(rep.lines)):
            (line_object, local_names, indent) = rep.lines[i]
            phrase = str(line_object)  #.render()
            if phrase not in phrases:
                phrases.append(phrase)
            phraseID = phrases.index(phrase) + 1
            solution['phraseIDs'].add(phraseID)
            lineDict = {
                'indent': indent,
                'phraseID': phraseID
            }
            solution['lines'].append(lineDict)
        for avar in rep.abstract_vars:
            if not avar.canon_name.endswith('__'):
                if avar not in variables:
                    variables.append(avar)
                varID = variables.index(avar) + 1
                solution['variableIDs'].add(varID)
        solution['number'] = rep.solnum
        solution['output'] = rep.output
        solution['members'] = stack.members
        solution['count'] = stack.count
        solution['phraseIDs'] = list(solution['phraseIDs'])
        solution['variableIDs'] = list(solution['variableIDs'])
        solutions.append(solution)

        var_obj_to_templates = {}
        for avar in stack.var_obj_to_templates:
            var_obj_to_templates[avar.canon_name] = {
                'templates': list(stack.var_obj_to_templates[avar]),
                'values': avar.sequence
            }
        avar_template_info[rep.solnum] = var_obj_to_templates

def create_template_info_output(stacks, incorrect_solutions, var_template_info):
    for stack in stacks:
        var_name_to_templates = {
            '__correct__': stack.representative.correct,
            '__members__': stack.members,
        }
        for var_obj in stack.var_obj_to_templates:
            if isinstance(var_obj, AbstractVariable):
                name = var_obj.canon_name
            else:
                name = var_obj.local_name + '_(local)'
            var_name_to_templates[name] = {
                'templates': list(stack.var_obj_to_templates[var_obj]),
                'values': var_obj.sequence
            }
        var_template_info[stack.representative.solnum] = var_name_to_templates
    for sol in incorrect_solutions:
        var_name_to_templates = { '__correct__': False }
        for lvar in sol.var_obj_to_templates:
            var_name_to_templates[lvar.local_name] = {
                'templates': list(sol.var_obj_to_templates[lvar]),
                'values': lvar.sequence
            }
        var_template_info[sol.solnum] = var_name_to_templates

def reformat_phrases(phrases):
    """
    Put the phrases list into the expected output format.
    """

    # TODO: feature spans?
    for i in range(len(phrases)):
        phrase = phrases[i]
        phrases[i] = {
            'id': i+1,
            'code': cgi.escape(phrase)
        }

def reformat_variables(variables):
    """
    Put the variables list into the expected output format.
    """

    for i in range(len(variables)):
        var = variables[i]
        variables[i] = {
            'id': i+1,
            'varName': var.canon_name,
            'sequence': var.sequence
        }

def create_avar_output(correct_abstracts):
    info = {}
    for avar in correct_abstracts:
        avar_info = {
            'values': avar.sequence,
            'templates': list(avar.templates) #[{'template': t[0], 'indices': t[1]} for t in avar.templates]
        }
        info[avar.canon_name] = avar_info
    return info


###############################################################################
## Dump output
###############################################################################

#from: http://stackoverflow.com/questions/8230315/python-sets-are-not-json-serializable
#and http://stackoverflow.com/questions/624926/how-to-detect-whether-a-python-variable-is-a-function
class ElenaEncoder(json.JSONEncoder):
    def default(self, obj):
       if isinstance(obj, set):
          return {'type':'set', 'list':list(obj)}
       if isinstance(obj, types.FunctionType):
          return {'type':'function'}
       return json.JSONEncoder.default(self, obj)

###############################################################################
## Run the pipeline!
###############################################################################
def run(folderOfData, destFolder):
    ensure_folder_exists(destFolder)
    def dumpOutput(data, filename, sort_keys=True, indent=4):
        filepath = path.join(destFolder, filename)
        with open(filepath, 'w') as f:
            json.dump(data, f, sort_keys=sort_keys, indent=indent, cls=ElenaEncoder)

    # try:
    #     with open('all_stacks.pickle', 'r') as f:
    #         all_stacks = pickle.load(f)
    # except:
    # Load solutions
    all_solutions = []
    populate_from_pickles(all_solutions, path.join(folderOfData, 'pickleFiles'))

    # Collect variables into AbstractVariables
    correct_abstracts = []
    correct_solutions, incorrect_solutions = [], []
    skipped_extract_sequences = extract_and_collect_var_seqs(
        all_solutions, correct_solutions, incorrect_solutions, correct_abstracts)

    find_canon_names(correct_abstracts)

    ########

    # Collect lines
    all_lines = []
    skipped_by_renamer = compute_all_lines(all_solutions,folderOfData,all_lines)

    # pprint.pprint(correct_abstracts[0].templates, indent=2)
    # return

    # dumpOutput(create_avar_output(correct_abstracts), 'avar_info.json')
    # return

    # print 'printing all_lines:'
    # for line in all_lines:
    #     pprint.pprint(line.getDict())

    # Canonicalize source and collect phrases
    # This is no longer doing anything relevant to the rest of the pipeline.
    # TODO: store the (former) output of this somewhere for ease of rendering?
    # this is the only place where name clashes between multiple copies of a
    # single abs. var. are handled.
    # skipped_rewrite = rewrite_all_solutions(all_solutions, folderOfData)

    # Stack solutions
    correct_stacks = []
    stack_solutions(correct_solutions, correct_stacks)

    print "Number of incorrect solutions:",len(incorrect_solutions)

    scores, threshold = find_template_info_scores(correct_abstracts)
    pprint.pprint(dict(scores), indent=2)
    # print sum(scores.values())

    # for i in range(2):
    #     for lvar in incorrect_solutions[i].local_vars:
    #         find_matching_var(lvar, correct_abstracts, scores)
    results = find_all_matching_vars(incorrect_solutions, correct_abstracts)
    dumpOutput(results, 'var_mappings.json')
    return
    # v = incorrect_solutions[0].local_vars[0]
    # find_matching_var(v, correct_abstracts)
    # for template, indices in v.templates:
    #     print render_template_indices(template, indices, v.local_name)
    # return

    # incorrect_stacks = []
    # stack_solutions(incorrect_solutions, incorrect_stacks)

    # pprint.pprint([s.members for s in incorrect_stacks], indent=2)

    # var_template_info = {}
    # create_template_info_output(correct_stacks, incorrect_solutions, var_template_info)
    # dumpOutput(var_template_info, 'var_template_info.json')
    # # dumpOutput([str(l) for l in all_lines], 'lines.json')

    # find_voting_stacks(correct_stacks, incorrect_solutions)
    # voters = {}
    # for sol in incorrect_solutions:
    #     voters[sol.solnum] = [s.representative.solnum for s in sol.voting_stacks]
    # dumpOutput(voters, 'voters.json')
    # return

    # with open('all_stacks.pickle', 'w') as f:
    #     pickle.dump(all_stacks, f)

    # Get output
    solutions = []
    phrases = []
    variables = []
    avar_template_info = {}
    create_output(all_stacks, solutions, phrases, variables, avar_template_info)
    reformat_phrases(phrases)
    reformat_variables(variables)

    dumpOutput(solutions, 'solutions.json')
    dumpOutput(phrases, 'phrases.json')
    dumpOutput(variables, 'variables.json')
    dumpOutput(avar_template_info, 'abstract_var_info.json')

    # print "skipped when extracting:", skipped_extract_sequences
    # print "skipped when rewriting:", skipped_rewrite
