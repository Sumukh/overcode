# overcode
OverCode's public repo (in development). See http://people.csail.mit.edu/elg/overcode for papers, posters, and talks.

## Running the pipeline (TL;DR)

1. Create a target directory. 
2. In the target directory, create a subdirectory called `data`
3. Copy into the subdirectory `data` the following:
    * one Python file per student submission
    * a correct solution named `answer.py` [Note: this correct solution needs only to pass all test cases. There may be many corret solutions. Only `answer.py`'s input-output behavior on test cases will be compared to student solutions.]
2. Next to the `data` subdirectory, add a `testCase.py` file. Each line in this file is a single test case, i.e., a Python function call, prepended by the command `print`. See below for an example. For more complicated test cases, see Notes on Test Cases below.
3. Execute the solutions on the testcases
    * In this repo's `src` directory, execute```python run_pipeline.py PATH_TO_TARGET_DIRECTORY --run-pre -n FUNCTION_NAME```
       * `-n FUNCTION_NAME` is optional, but helps us better tidy up solutions before execution
       * `--run-pre` means "run the preprocessor" which is what we call the code that executes and logs the behavior of solutions. It only needs to be done once, unless the test cases change.
4. Run the analysis pipeline on the results of executing the solutions
    * In this repo's `src` directory, execute ```python run_pipeline.py PATH_TO_TARGET_DIRECTORY --run-pipeline```
       * `-d` is optional; it turns on the calculation of a pairwise distance metric, a heuristic of code similarity between solutions, which is slow for > a few hundred solutions
       * `-g PATH_TO_MITX_GRADER/grade_....py` is optional. If you don't have one, the pipeline compares the output of each solution to the answer.py's output (as strings) with `==`.

Example `testCase.py`:

    print student_defined_function('foo')
    print student_defined_function('bar')

## Friendly Utility Functions (TL;DR)

If you wan to extract solutions from a csv where each row is of the form STUDENT_ID, TIME_STAMP, GRADE, NUMBER_OF_ATTEMPTS, SOLUTION, run the function `extract_solutions_final.py` on it to produce data of the form expected by the pipeline like this: 
`python testcase_making/extract_solutions_final.py PATH_TO_CSV/CSV_NAME.CSV PATH_TO_WHERE_FOLDER_OF_DATA_WILL_BE_CREATED`

Here's an example of a row in the expected CSV format:

```['Jon Snow', '2016-05-16 18:21:18+00:00', '1.0', '3', 'def stock_sim(trials, price):\r\n    """\r\n    trials: integer, number of trials to run\r\n    price: float, starting price of the stock\r\n    Runs a Monte Carlo simulation, \'trials\' times. \r\n    In each trial you determine the price of the stock \r\n    at the end of 20 days, assuming that the closing price \r\n    at each day is drawn from a normal distribution with a \r\n    mean of 1.002 times the closing price of the previous \r\n    day and a standard deviation of 0.2.\r\n    Returns: \r\n    a tuple of (observed mean possible final stock price, \r\n                lower bound for the 95% confidence interval, \r\n                upper bound for the 95% confidence interval) \r\n    after 20 days over \'trials\' trials\r\n    """\r\n    def single_trial(num_days, start_price):\r\n        cur_price = start_price\r\n        for x in range(num_days):\r\n            cur_price = random.gauss(1.02*cur_price, 0.2)\r\n        return cur_price \r\n    \r\n    price_list = []\r\n    for trial in range(trials):\r\n        price_list.append(single_trial(20, price))\r\n        \r\n    mean = float(sum(price_list))/trials\r\n    std = pylab.std(price_list)\r\n    SE = std/(trials**0.5)\r\n    return (mean, mean-1.96*SE, mean+1.96*SE)']```

Here's an example of calling the function (from the `src` directory):

```python testcase_making/extract_solutions_final.py ~/Dropbox/overcode_data/6.0002final/q8/q8_stocksim.csv ~/Dropbox/overcode_data/6.0002final/q8/```

## Running the pipeline (The Long Version)

Use the `src/run_pipeline.py` script from the command line to interact with the various parts of the OverCode pipeline. Run `python run_pipeline.py -h` for a description of the available arguments.

### Preprocessor
The preprocessor actually executes student solutions using Philip guo's execution logger. From within the src directory, run the preprocessor with `python run_pipeline.py path/to/target/directory -P`. Instead of `-P`, `--run-pre` will work as well.

The name of the student-defined function being called can be supplied with `-n` or `--funcname`, like this: `-n name_of_function`. Any calls to the named function within a submission will be removed when the code is tidied.

The given target directory must contain two things:

* A subdirectory called "data", containing one Python file per student submission, and an official correct solution named `answer.py`.

* A `testCase.py` file, where each line of the file is a single test case, i.e., a Python function call. Test cases are often just single calls to a student-defined function, but can also be more complicated functions. See Notes on Test Cases below.

The `extract_solutions_final.py` script, located in `src/testcase_making`, will turn a CSV of student submissions into a directory of Python files as expected by the preprocessor. Run it with `python extract_solutions_final.py path/to/CSV path/to/output/directory`. This script creates a directory called "data" within the specified output directory and fills it with (anonymized) student submissions. It also writes a file called `mapping.txt` in `src/testcase_making` which contains the mapping between student usernames and anonymized identifiers.

The CSV parsing script may complain about bad rows. If that happens, it probably means there is an unescaped double quote (") within a student submission. To fix it, find the problematic quotation mark (the script prints out each row as it parses it, so just search within the CSV for a nearby row), and replace it with a single quote (') or an escaped double quote (\") instead.

The `answer.py` file must be manually copied into the data folder.

#### Notes on Test Cases

**Test cases must print their output!** Otherwise, the pipeline won't be able to compare the results of student submissions to the correct answer. This usually means that each line of `testCase.py` is simply a print statement followed by a function call, like this:

    print student_defined_function('foo')
    print student_defined_function('bar')

However, test cases can also be more complicated. The output of each test is simply compared to the output of the supplied correct answer, so tests can be anything. To use more complicated tests, first add a variable to  `src/affixes.py` containing the literal source of the test definitions (or any other extra code) as a string. There are already some examples defined in `affixes.py`, but here's a simple pair of test cases:

```python
testcase_definitions_example = r"""
def test_0():
    # checks that my_list isn't mutated
    my_list = []
    student_defined_function(my_list)
    print my_list  # should be []

def test_1():
    # checks return value
    print student_defined_function([])
"""
```

Next, change the `import` statement in `src/pipeline_preprocessing.py` to import the newly defined test case definitions (see the comments within the code). Finally, define a `testCase.py` file as usual. It should simply call the extra functions, like this:

    test_0()
    test_1()

#### Output of the preprocessor (For reference)

The preprocessor adds three subdirectories to the "data" directory: `tidyData`, `augmentedData`, and `pickleFiles`. `tidyData` contains submissions with comments removed, whitespace normalized, etc. `augmentedData` contains the tidied submissions with any extra code appended/prepended, like the testcase definitions described above. `pickleFiles` is the important folder! This has the serialized version of the program traces and outputs of each submission, and is what the pipeline reads in.

### Analysis Pipeline

The pipeline is where the magic happens. From within the src directory, run the pipeline with `python run_pipeline.py path/to/target/directory -p -d`. Instead of `-p`, `--run-pipeline` will work as well. The target directory is the same as described above. The `-d` flag tells the pipeline to compute the pairwise distances between stacks. This is necessary for the view, but will be very slow with extra large datasets, so can be disabled by excluding the flag.

An MITx grader can be specified by adding the `-g` flag, like this: `-g path/to/MITx/grader`. The path should include the `grade_*.py` part. The grader is used for comparing the output of student submissions to the output of the correct answer. If no grader is supplied, the comparison defaults to comparing the results (as strings) with `==`.

The pipeline reads in the pickle files output by the preprocessor. There is no need to rerun the preprocessor once those have been generated.

#### Output of the pipeline (For reference)

The pipeline adds an "output" subdirectory to the target directory and creates several json files in that subdirectory. The most important json files are `phrases.json` and `solutions.json` – these are used by the view. The other output files are only for debugging or reference.

`phrases.json` contains a list of objects representing lines of code with the variables renamed, which we call phrases. Each object has the following keys:
* `code`: string, the actual text of this phrase
* `id`: integer, a unique id for this phrase. Indexed from 1.
* `corresponding_lines`: list of integers, indicating which Line objects generated this phrase. Each integer corresponds to the id of a Line in `lines.json`.
Only the first two keys, `code` and `id`, are used by the view.

`solutions.json` contains a list of objects representing stacks, that is, groups of one or more student submissions. The name is slightly misleading – a better name would probably be `stacks.json`. This is where most of the information is stored. Each object has the following keys:
* `correct`: boolean, true if the submissions making up this stack passed all test cases, false otherewise
* `count`: integer, the number of submissions contained in this stack
* `error_vector`: list of booleans, one per test case. true indicates a passed test case, false indicates a failed test case
* `id`: integer, a unique id for this stack. Indexed from 1.
* `line_ids`: set of integers, indicating which Line objects are associated with the solution(s) in this stack. Not used by the view
* `lines`: list of objects representing the phrases in this stack. This is what the view uses to reassemble the code for this stack. This field should probably be called `phrases` instead. Each object has these keys:
  * `indent`: integer. The number of spaces to indent this phrase
  * `line_obj_ID`: integer indicating which Line object generated this phrase. Corresponds to the id of a line in `lines.json`. Not used by the view
  * `phraseID`: integer. Corresponds to the id of a phrase in `phrases.json`.
* `members`: list of strings. The identifiers (i.e., filenames without `.py`) of the submission(s) that belong to this stack
* `num_passed_tests`: integer. How many test cases this stack passed
* `number`: string. The identifier of the representative for this stack
* `phraseIDs`: set of integers. Indicates which phrases are associated with this stack, not necessarily in order of appearence
* `stack_distances`: object mapping the id of each stack (as a string, for some reason) to the distance between that stack and this stack (as a float between 0 and 1.0). Includes itself. So if there are four stacks in total, this object will have the keys `"1"`, `"2"`, `"3"`, and `"4"`.
* `test_input_outputs`: object mapping the text of each testcase (a string) to the output of this stack on that testcase (also a string)
* `testcases`: list of strings. The ordered list of test cases on which this stack was run. The same as the keys of `test_input_outputs`, but ordered.
* `total_num_tests`: integer, the total number of test cases.
* `variable_ids`: list of integers indicating which variables are present in this stack. Each integer corresponds to the id of a variable in `variables.json`. Not used by the view

## View

### OverCode

cd into the ui folder, run a server in the folder from the commandline, and give ?src=DATASET where DATASET is a key in the config.json file.

### GroverCode (OverCode for grading)

The GroverCode user interface is implemented in [Meteor](http://www.meteor.com/). The user interface code is located in the `overcode-meteor` directory.

#### Setting up the view

Open `overcode-meteor/server/server.js`. Underneath the comment that says "Define paths here", define the three variables `results_path`, `data_path`, and `logging_path` so that they point to the appropriate locations on your machine. See inline comments.

Change the `RELOAD` constant to true to load the analyzed data on server startup. **Change it back to false before doing any grading.** If it's set to true, the log will not be replaced when the server restarts, so no grades will be permanently lost, but the state of the interface will be reset, so none of the previous grades will be displayed in the OverCode interface.

#### Running the view

In the command line, navigate to the `overcode-meteor` directory and run `meteor`. Navigate to localhost:3000.

#### More view customization

Warning: the view code is not very clean and could use refactoring. Mess with it at your own risk. More maintainable configuration, e.g., a config file, would be helpful as well.

The test case display currently assumes that test cases are of the form `print <function call>` and slices off the `print` part. This is controlled around line 90 in both `overcode-meteor/client/elena_client.js` and `overcode-meteor/client/client.js`, in this line:

    test: test.slice(6), // remove 'print '

Change this to something else to display nicer test case descriptions for custom test cases. Unfortunately there is no existing infrastructure for extracting, say, test docstrings.


## Description of Overcode Pipeline (as of late March)
### Interesting Dependencies
Philip Guo's variable renamer and python execution logger
### Interesting Data Structures
We implemented a "setlist" to help us organize information. It's a set, stored as a list, where order represents the order in which items were added.

### Interesting Objects

#### Variable Objects
Variable objects represent a specific variable within a specific program.

#### Abstract Variable
An abstract variable, distinguished (for now) from other abstract variables by its sequence of values. Stores the histogram of names given to it in student solutions, and which student solutions those are.

### Line Objects
Line objects contain a line of code (without any indent specified) with blanks for variables. The blanks have corresponding Abstract Variables, based on the whole solution and the whole collection of solutions this line is in. The blanks also have a (sequence or set?) of values plugged into them during the solution's execution, and these values are stored.

#### Solution Objects
Solution objects contain information about how they are written and how they behave. They also store a unique id (`solnum`).

##### Input-Output Behavior
Solution objects store what test cases were run on them, in what order (`testcases`), and what output they produced (`output`). 

##### Correctness
Solution objects store whether those test cases passed or failed to produce acceptable output (`error_vector`), and whether they passed *all* test cases (`correct`).

##### Internal Dynamics
Solution objects store traces of their internal behavior in response to each test case (`testcase_to_trace`). Based on these traces, we derive:

*Variable View*

Solution objects store the behavior of all local variables logged during execution and which of those variables correspond to Abstract Variable Objects.

*Line View*

Solution objects store lines as tuples of templates (lines with blanks where the variables would be), local names for those variable blanks, sets of values that those blanks took on during execution, and the line's indent in the program.

### Interesting Heuristics

In the original OverCode work, we clustered canonicalized solutions so teachers could get a sense of the common and uncommon solutions. In this expanded OverCode work, we support the arduous grading processes in introductory python courses like 6.0001. We canonicalize incorrect solutions as well as correct solutions, and sort solutions by similarity heuristics, rather than cluster size.

#### Recommendation heuristic

We're interested in helping teachers "bring more context with them" when they're jumping from solution to solution during exhaustive grading.

