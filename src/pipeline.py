import cgi
from collections import Counter
# import inputs
import json
import os
from os import path
import pickle
import re
import subprocess
import sys
import types

# from generate_json_trace import *
from external import get_python_fnames_pipeline as fnames
from external import (
    identifier_renamer,
    rewrite_pipeline,
)
from pipeline_util import ensure_folder_exists


# Grab parameters from inputs
# inputArgs = inputs.argDict[sys.argv[1]]
baseDir = '../../overcode_data/6.0001_dotprod'
folderOfData = path.join(baseDir, 'data') #inputArgs['folderOfData']
destFolder = path.join(baseDir, 'output')  #inputArgs['destFolder']
testCasePath = path.join(baseDir, 'testCase.py')
with open(testCasePath, 'r') as f:
    testCases = f.read();
# testCases = inputArgs['testCases']
funcName = 'dotProduct' #inputArgs['testedfuncname']

# Constants and initial lists
removePrintStatements = False
wrapInFunction = True
stopOnError = True
alreadyTidied = False

getRidOfStars = True
rewrite_pipeline_toggle = False
src_skipped_by_philip = []
solnum_skipped_by_philip = []
numSkippedSols_2b = []
numSkippedSols_NoSharedVars = []
sharedVarThreshold = 1
otherReturned = []
tidyUp = True
# solnum -> trace
progTraceDictAll = {}
argAndReturnVarInfo = {}

numSkippedSols_Tidy = []
numSkippedSols_RemoveComments = []
numSkippedSols_Logger = []
numSkippedSols_localcommonVarClash = []

def populate_from_pickles(pickleSrc, formattedSrc, formattedExtn='.py.html'):
    print "Loading data"
    for filename in os.listdir(pickleSrc):
        solNum = filename.split('.')[0]
        solNumInt = int(solNum)
        print solNum

        with open(path.join(pickleSrc, filename), 'r') as f:
            unpickled = pickle.load(f)
        progTraceDictAll[solNum] = unpickled['trace']

        argAndReturnVarInfo[solNumInt] = {}
        argAndReturnVarInfo[solNumInt]['args'] = unpickled['args']
        argAndReturnVarInfo[solNumInt]['returnVars'] = unpickled['returnVars']
        # with open(path.join(formattedSrc, solNum + formattedExtn), 'r') as f:
        #     argAndReturnVarInfo[solNumInt]['code'] = f.read()

populate_from_pickles(path.join(folderOfData, 'pickleFiles'), path.join(folderOfData, 'tidyDataHTML'))


###############################################################################
## Stacey has worked up to here.
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


def dumpOutput(data, filename, sort_keys=True, indent=4):
    filepath = path.join(destFolder, filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, sort_keys=sort_keys, indent=indent, cls=ElenaEncoder)


ensure_folder_exists(destFolder)

'''Linearly accumulate variables that have the same sequence of values across
multiple solutions'''
def extractSequence(column):
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

# sequence of values is extracted and compared to what we already have
def isThisVarSeqInOurDict(localVarData):
    for tempVarName, tempVarData in dictTempNameToSequence.iteritems():
        if tempVarData == extractSequence(localVarData):
            return tempVarName
    return None

# temporary variable name to (local name, solution number)
dictOfNamesAndFilesIndexedByVarSeqTempName = {}
dictTempNameToSequence = {}
dictReturnValues = {}

def getVarEquivsAcrossAllSolsLinear():
    numSkippedSols_tooLong = []

    # This will not remove duplicates within one solution
    printHowMany = float("inf")
    printCtr = 0
    for k,v in progTraceDictAll.iteritems():
        # print k,v
        # k is the solution number, v is the trace of variable names and values

        # Extracts the return value from the trace
        if '__return__' not in v.keys():
            # print k, ' FAILED TO EXECUTE PROPERLY\n'
            numSkippedSols_tooLong.append(k)
            continue
        else:
            # print 'whole __return__ record: ',v['__return__']
            # # Extract returned answer from list of tuples
            # print 'returned answer: ', v['__return__'][-2][1]

            returnedAns = v['__return__'][-2][1]
            # solution number => return value
            dictReturnValues[k] = returnedAns
        

        for localVarName, localVarData in v.iteritems():
            if localVarName.startswith('__'):
                continue
            tempVarName = isThisVarSeqInOurDict(localVarData)
            theExtractedSequence = extractSequence(localVarData)
            # print localVarName, tempVarName, theExtractedSequence
            if len(theExtractedSequence)==1 and type(theExtractedSequence[0]) is str:
                if theExtractedSequence[0].startswith('__'):
                    # print 'just a function definition'
                    continue
            if tempVarName != None:
                # we already have the variable sequence in our dict
                dictOfNamesAndFilesIndexedByVarSeqTempName[tempVarName].append((localVarName,k))
            else:
                if len(dictOfNamesAndFilesIndexedByVarSeqTempName.keys()) == 0:
                    # 0 is a temp name here
                    dictOfNamesAndFilesIndexedByVarSeqTempName[0] = [(localVarName,k)]
                    dictTempNameToSequence[0] = theExtractedSequence
                else:
                    maxVarName = max(dictOfNamesAndFilesIndexedByVarSeqTempName.keys())
                    newTempVarName = maxVarName + 1
                    dictOfNamesAndFilesIndexedByVarSeqTempName[newTempVarName] = [(localVarName,k)]
                    dictTempNameToSequence[newTempVarName] = theExtractedSequence
        printCtr+=1
        if printCtr > printHowMany:
            break
    return numSkippedSols_tooLong

print "Getting variable equivalents"
numSkippedSols_tooLong = getVarEquivsAcrossAllSolsLinear()


'''Begin populating a json file (dictForJson) that is indexed by
the solution name and includes things like the weird and common variable names'''

print "Populating dictForJson"
dictForJson = {}
for nums in sorted(set(map(len, dictOfNamesAndFilesIndexedByVarSeqTempName.values())),reverse=True):
    # print
    # print 'Num Of Files: ', nums
    for k,v in dictOfNamesAndFilesIndexedByVarSeqTempName.iteritems():
        if nums == len(v):
            # print 'Temp Name: ', k
            # print 'Var Sequence: ', dictTempNameToSequence[k]
            # print 'Example file: ', v[0:10]
            # for (localVar, solname) in v[0:10]:
            #     print localVar, solname
            # print
            if nums == 1:
                # TODO: is the iteritems not necessary?
                for (localVar, solname) in v: #.iteritems():
                    # print localVar, solname, dictForJson.keys()

                    if str(solname) in dictForJson.keys():
                        # print 'solname in dictForJson.keys()'
                        dictForJson[solname]['weirdVars'].append(localVar) #+' '+seqStr)
                    else:
                        dictForJson[solname]={}
                        dictForJson[solname]['weirdVars']= [localVar] #+' '+seqStr]


'''Determine what the common name of a variable should be
by extracting the most common variable name'''
def extractVarName(tempName):
    accumulatedVarNames = []
    accumulatedVarNames+= [tup[0] for tup in dictOfNamesAndFilesIndexedByVarSeqTempName[tempName]]
    cnt = Counter()
    for word in accumulatedVarNames:
        try:
            cnt[word] += 1
        except:
            print word, ' failed'
    return cnt.most_common(1)[0][0]


dictOfSeqAndCommonNameByTempVar = {}
dictOfNumFilesByCommonName = {}

print "Extracting variable names"
# Sweep through and accumulate file lengths into a dict
for tempKey, listOfFileAndVars in dictOfNamesAndFilesIndexedByVarSeqTempName.iteritems():
    numFiles = len(listOfFileAndVars)
    if numFiles > sharedVarThreshold:

        canonName = extractVarName(tempKey)

        #update the max files associated with a common name
        if canonName in dictOfNumFilesByCommonName:
            dictOfNumFilesByCommonName[canonName].append(numFiles)
            dictOfNumFilesByCommonName[canonName] = sorted(dictOfNumFilesByCommonName[canonName],reverse=True)
        else:
            dictOfNumFilesByCommonName[canonName] = [numFiles]

# pprint.pprint(dictOfNumFilesByCommonName)


# Write out dictOfNamesAndFilesIndexedByVarSeqTempName to json so I can visualize it
print "Writing variables by varSeqTempName"
dumpOutput(dictOfNamesAndFilesIndexedByVarSeqTempName,
           'variablesByVarSeqTempName.json')
# with open(path.join(destFolder, 'variablesByVarSeqTempName.json'), 'w') as outfh:
#     json.dump(dictOfNamesAndFilesIndexedByVarSeqTempName, outfh, sort_keys=True, indent=4, cls=ElenaEncoder)


'''Add more info to dictForJson, like the common names for each variable, and
modifiers to that common name, to indicate with sequence it takes on...'''

print "Adding common names"
dictOfSeqByCommonNamePlusSuffix = {}
for tempKey, listOfFileAndVars in dictOfNamesAndFilesIndexedByVarSeqTempName.iteritems():
    numFiles = len(listOfFileAndVars)
    # print 'tempKey, numFiles', tempKey, numFiles
    if numFiles > sharedVarThreshold:
        dictOfSeqAndCommonNameByTempVar[tempKey] = {}
        dictOfSeqAndCommonNameByTempVar[tempKey]['howManyFiles'] = numFiles

        canonName = extractVarName(tempKey)
        # print canonName

        offSetFromMax = dictOfNumFilesByCommonName[canonName].index(numFiles)
        if offSetFromMax > 1:
            canonAppend = '___' + str(offSetFromMax)
        else:
            canonAppend = ''
        # print canonAppend

        dictOfSeqAndCommonNameByTempVar[tempKey]['commonName'] = canonName
        dictOfSeqAndCommonNameByTempVar[tempKey]['commonNameWithSuffix'] = canonName+canonAppend

        seqStr = dictTempNameToSequence[tempKey]
        # print str(seqStr)

        dictOfSeqByCommonNamePlusSuffix[canonName+canonAppend] = seqStr

        dictOfSeqAndCommonNameByTempVar[tempKey]['sequence'] = seqStr
        for localVarName, solNum in listOfFileAndVars:
            if solNum in dictForJson.keys():
                if 'sharedVars' in dictForJson[solNum]:
                    dictForJson[solNum]['sharedVars'].append(canonName+canonAppend) #+' '+seqStr)
                    dictForJson[solNum]['localVars'].append(localVarName)
                    dictForJson[solNum]['commonNameAppend'].append(canonAppend)
                    dictForJson[solNum]['commonName'].append(canonName)
                else:
                    dictForJson[solNum]['sharedVars']= [canonName+canonAppend] #+' '+seqStr]
                    dictForJson[solNum]['localVars'] = [localVarName]
                    dictForJson[solNum]['commonNameAppend'] = [canonAppend]
                    dictForJson[solNum]['commonName']= [canonName]
            else:
                dictForJson[solNum]={}
                dictForJson[solNum]['sharedVars']= [canonName+canonAppend] #+' '+seqStr]
                dictForJson[solNum]['localVars'] = [localVarName]
                dictForJson[solNum]['commonNameAppend'] = [canonAppend]
                dictForJson[solNum]['commonName']= [canonName]
# pprint.pprint(dictOfSeqAndCommonNameByTempVar)
# pprint.pprint(dictForJson)

print "Writing common variable legend and main json file"
dumpOutput(dictOfSeqByCommonNamePlusSuffix, 'commonVarLegend.json')
dumpOutput(dictForJson, 'dictForJson.json')
# with open(path.join(destFolder, 'commonVarLegend.json'),'w') as jsonFile:
    # json.dump(dictOfSeqByCommonNamePlusSuffix, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)

# with open(path.join(destFolder, 'mainDict.json'),'w') as jsonFile:
    # json.dump(dictForJson, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)


def getFreeVars(dictOfLocalAndCommonVarNames, argAndReturnData):
    freeVars = {}
    for k,v in dictOfLocalAndCommonVarNames.iteritems():
        freeVars[k] = []
        if 'localVars' in v.keys():
            for localVar in v['localVars']:
                if localVar not in argAndReturnData[int(k)]['args'] and localVar not in argAndReturnData[int(k)]['returnVars']:
                    freeVars[k].append(localVar)
        if 'weirdVars' in v.keys():
            print 'there are weirds!',k, v['weirdVars']
            for weirdVar in v['weirdVars']:
                if weirdVar not in argAndReturnData[int(k)]['args'] and weirdVar not in argAndReturnData[int(k)]['returnVars']:
                    freeVars[k].append(weirdVar)
        argAndReturnData[int(k)]['studentCreatedVars'] = freeVars[k]
    return freeVars

print "Getting free variables"
freeVars = getFreeVars(dictForJson,argAndReturnVarInfo)

print "Writing arg and return value info and free vars"
dumpOutput(argAndReturnVarInfo, 'argAndReturnVarInfo.json')
dumpOutput(freeVars, 'freeVars.json')
# with open(path.join(destFolder, 'argAndReturnVarInfo.json'), 'w') as outfh:
    # json.dump(argAndReturnVarInfo, outfh, sort_keys=True, indent=4, cls=ElenaEncoder)

# with open(path.join(destFolder, 'freeVars.json'),'w') as jsonFile:
    # json.dump(freeVars, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)


def produceFooBarBazJson(argsAndCode):
    loweringfunc = lambda s: s[:1].lower() + s[1:] if s else ''
    import collections
    import copy
    listOfSolDictsForTable = []
    for solnum,soldata in argsAndCode.iteritems():
        dictWithName = collections.OrderedDict()
        dictWithName['solution'] = int(solnum)
        if 'args' in soldata.keys():
            dictWithName['arguments'] = sorted([loweringfunc(listelement) for listelement in soldata['args']]) #soldata['args']
        else:
            dictWithName['arguments'] = []
        studCreatedVars = []
        if 'studentCreatedVars' in soldata.keys():
            studCreatedVars += soldata['studentCreatedVars']
        if 'returnVars' in soldata.keys():
            studCreatedVars += soldata['returnVars']
        dictWithName['studentCreatedVariables'] = sorted([loweringfunc(listelement) for listelement in studCreatedVars])

        listOfSolDictsForTable.append(dictWithName)
    return listOfSolDictsForTable

print "Producing and writing solution dicts for table"
listOfSolDictsForTable = produceFooBarBazJson(argAndReturnVarInfo)
dumpOutput(listOfSolDictsForTable, 'listOfSolDictsForTable.json')
# with open(path.join(destFolder, 'listOfSolDictsForTable.json'), 'w') as outfile:
    # json.dump(listOfSolDictsForTable, outfile)


'''Collect all common vars into a single list.'''

print "Collecting common variables"
allCommonVar = set()
for sol,varDict in dictForJson.iteritems():
    if 'sharedVars' in varDict.keys():
        allCommonVar.update(varDict['sharedVars'])

# print 'allCommonVar', allCommonVar


'''Create JSON with format necessary for Exhibit'''
dictForExihibit = {}

dictForExihibit['items'] = []
dictForExihibit['properties'] = {}
dictForExihibit['types'] = {}

dictForExihibit['types']['Answer'] = {}
dictForExihibit['types']['Answer']['pluralLabel'] = 'Answers'

#numSkippedSols_1 = []
numSkippedSols_2 = []
numSkippedSols_commonVarClash = []
numSkippedSols_weirdVarClash = []
flagged = False
ensure_folder_exists(folderOfData+'/tidyDataCanonicalized/')
ensure_folder_exists(folderOfData+'/tidyDataCanonicalizedHTML/')

phraseCounter = Counter()
tabCounter = {}

lilCtr = 0

numSkippedSols_6 = []

print "Creating dict for Exhibit"
for solNum, solDict in dictForJson.iteritems():
    flagged = False

    lilCtr += 1
    # print lilCtr

    try:
        if len(solDict['sharedVars'])>len(set(solDict['sharedVars'])):
            print 'this solution has multiple indistinguishable instances of a shared variable; fixing!'
            numSkippedSols_commonVarClash.append(solNum)

            # print solNum
            # print solDict

            for sv in solDict['sharedVars']:
                # print sv
                indices = [i for i, x in enumerate(solDict['sharedVars']) if x == sv]
                # print indices
                if len(indices)>1:
                    # print 'multiples printed'
                    for ind in indices:
                        if not solDict['sharedVars'][ind] == solDict['localVars'][ind]: #if it's common and local names are i, don't make it i_i
                            solDict['sharedVars'][ind] = solDict['sharedVars'][ind]+'_'+solDict['localVars'][ind]+'__'
                        # print ind, solDict['sharedVars'][ind]
    except:
        print 'no sharedVars in vardict... Why?', sol, varDict
        numSkippedSols_NoSharedVars.append(solNum)

    # print solNum
    tempDict = solDict.copy()
    tempDict['type'] = 'Solution'
    tempDict['label'] = solNum
    tidyPath = path.join(folderOfData, 'tidyData', solNum + '.py')
    try:
        tempDict['fnames'] = fnames.main(tidyPath)
    except:
        print 'warning: no fnames for ', solNum

    with open(tidyPath,'U') as f:
        read_data = f.read()

    renamed_src = read_data

    extraToken = '_temp' # a * didn't work so well
    if 'sharedVars' in tempDict.keys():
        for i in range(len(tempDict['sharedVars'])):
            locVarName = tempDict['localVars'][i]
            # extracts just the name, not the sequence of values we appended
            sharedVarNameWithStar = tempDict['sharedVars'][i]+extraToken 
            try:
                renamed_src = identifier_renamer.rename_identifier(renamed_src, locVarName,sharedVarNameWithStar)
            except:
                print 'Could not run Philip renamer; skipping!'
                src_skipped_by_philip.append(renamed_src)
                solnum_skipped_by_philip.append(solNum)
                flagged = True
            if rewrite_pipeline_toggle:
                try:
                    renamed_src = rewrite_pipeline.reorderVariables(renamed_src,togVar)
                except:
                    print 'skipping!'
                    numSkippedSols_2b.append(solNum)
                    flagged = True

        if getRidOfStars:
            for i in range(len(tempDict['sharedVars'])):

                sharedVarNameWithStar = tempDict['sharedVars'][i]+extraToken
                sharedVarNameWithOutStar = tempDict['sharedVars'][i]

                try:
                    renamed_src = identifier_renamer.rename_identifier(renamed_src, sharedVarNameWithStar,sharedVarNameWithOutStar)
                except:
                    print 'Could not run Philip renamer; skipping!'
                    src_skipped_by_philip.append(renamed_src)
                    solnum_skipped_by_philip.append(solNum)
                    flagged = True

    if 'weirdVars' in tempDict.keys():
        for weirdInstance in tempDict['weirdVars']:
            if weirdInstance in allCommonVar:
                numSkippedSols_weirdVarClash.append(solNum)
                # print renamed_src
                try:
                    renamed_src = identifier_renamer.rename_identifier(renamed_src, weirdInstance,weirdInstance+'__')
                except:
                    print 'Could not run Philip renamer; skipping!'
                    src_skipped_by_philip.append(renamed_src)
                    solnum_skipped_by_philip.append(solNum)
                    flagged = True
                # print renamed_src

    tempDict['canonicalPYcode'] = [el.strip() for el in renamed_src.split('\n') if not (el == '')]
    with open(folderOfData+'/tidyDataCanonicalized/'+solNum+".py",'w') as g:
        g.write(renamed_src)

    phraseCounter.update([el.strip() for el in renamed_src.split('\n')  if not (el == '')])
    tempDict['canonicalPYcodeIndents'] = []
    for unstrippedLine in renamed_src.split('\n'):
        if not (unstrippedLine == ''):
            strippedLine = unstrippedLine.strip()
            leadingSpace = len(unstrippedLine) - len(strippedLine) #how much was lobbed off?
            tempDict['canonicalPYcodeIndents'].append(leadingSpace)
            if strippedLine in tabCounter.keys():
                tabCounter[strippedLine].update([leadingSpace])
            else:
                tabCounter[strippedLine] = Counter()
                tabCounter[strippedLine].update([leadingSpace])


    if not flagged:
        subprocess.call("pygmentize -O style=colorful,linenos=1 -o "+folderOfData+'/tidyDataCanonicalizedHTML/'+solNum+".py.html"+" "+folderOfData+'/tidyDataCanonicalized/'+solNum+".py", shell=True)

        with open(folderOfData+'/tidyDataCanonicalizedHTML/'+solNum+".py.html",'U') as myfile:
            htmlCode = myfile.read()
            htmlCodeFormatted = htmlCode.replace("\"","'").replace("\n","<br>")
            tempDict['code'] = htmlCodeFormatted
        dictForExihibit['items'].append(tempDict)
        # print "len(dictForExihibit['items'])", len(dictForExihibit['items'])

print "Writing dictForExihibit and phraseAndTabCounter"
dumpOutput(dictForExihibit, 'dictForExihibit.json')
# with open(path.join(destFolder, 'dictForExihibit.json'),'w') as jsonFile:
    # json.dump(dictForExihibit, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)

# pprint.pprint( phraseCounter )
# pprint.pprint( tabCounter )

phraseAndTabCounter = {}
phraseAndTabCounter['phraseCounter'] = phraseCounter
phraseAndTabCounter['tabCounter'] = tabCounter

#this includes phrases and such that never made it into the other json files because of skipping sols
dumpOutput(phraseAndTabCounter, 'phraseAndTabCounter.json')
# with open(path.join(destFolder, 'phraseAndTabCtr.json'),'w') as jsonFile:
    # json.dump(phraseAndTabCounter, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)


'''Create JSON with format necessary for D3 prototype'''
def returnSameAnswerQ(list,newSolnum):
    return True

theJSON = dictForExihibit.copy()
dictOfRepresentatives = {}
dictOfRepresentatives[theJSON['items'][0]['label']]= {}
dictOfRepresentatives[theJSON['items'][0]['label']]['rep'] = theJSON['items'][0]
dictOfRepresentatives[theJSON['items'][0]['label']]['count'] = 1
dictOfRepresentatives[theJSON['items'][0]['label']]['members'] = [theJSON['items'][0]['label']]

print "Formatting for D3 prototype"
for JSONitem in theJSON['items'][1:]:
    added = False
    for groupID, REPitem in dictOfRepresentatives.iteritems():
        if set(REPitem['rep']['canonicalPYcode']) == set(JSONitem['canonicalPYcode']): #REPitem['rep']['code'] == JSONitem['code']: #CHANGE THIS TO COMPARE SETS OF tab-stripped CANOICALIZED PY LINES
            if returnSameAnswerQ(REPitem['members'],JSONitem['label']):
                REPitem['count']+=1
                REPitem['members'].append(JSONitem['label'])
                added = True
                continue
    if not added:
        dictOfRepresentatives[JSONitem['label']] = {'rep': JSONitem, 'count': 1, 'members' : [JSONitem['label']] }

# pprint.pprint(dictOfRepresentatives)

print "Writing repDict"
dumpOutput(dictOfRepresentatives, 'repDict.json')
# with open(path.join(destFolder, 'repDict.json'),'w') as jsonFile:
#     json.dump(dictOfRepresentatives, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)

print "Finding misfits"
misfitTotal = 0
misfitMembers = []
for k, v in dictOfRepresentatives.iteritems():
    if v['count']==1:
        misfitTotal += 1
        misfitMembers.append(k)

repCounts = []
repCounts.append(('misfits',misfitTotal))
for k, v in dictOfRepresentatives.iteritems():
    if v['count'] != 1:
        repCounts.append((k, v['count']))

newlist = sorted(repCounts, key=lambda k: k[1],reverse = True)

# print newlist

repDataDict = {}
repDataDict['misfitMembers']= misfitMembers
repDataDict['repCountsSorted'] = newlist

print "Writing sorted rep dict"
dumpOutput(repDataDict, 'repDictSorted.json')
# with open(path.join(destFolder, 'repDictSorted.json'),'w') as jsonFile:
#     json.dump(repDataDict, jsonFile, sort_keys=True, indent=4, cls=ElenaEncoder)


raw_solutions = dictOfRepresentatives
solutions = []
phrases = []
variables = []
sequences = []

# TODO: figure out what this is doing
print "Something with phrases"
for groupID, groupDescription in raw_solutions.iteritems():
    solution = {'code': groupDescription['rep']['code']}
    solution['phraseIDs'] = set()
    solution['variableIDs'] = set()
    solution['lines'] = []
    for i in range(len(groupDescription['rep']['canonicalPYcode'])):
        phrase = groupDescription['rep']['canonicalPYcode'][i]
        if phrase not in phrases:
            phrases.append(phrase)
        phraseID = phrases.index(phrase) + 1
        solution['phraseIDs'].add(phraseID)
        lineDict = {}
        lineDict['indent'] = groupDescription['rep']['canonicalPYcodeIndents'][i]
        lineDict['phraseID'] = phraseID
        solution['lines'].append(lineDict)
    if 'sharedVars' in groupDescription['rep'].keys():
        for sharVar in groupDescription['rep']['sharedVars']:
            if not sharVar.endswith('__'):
                if sharVar not in variables:
                    variables.append(sharVar)
                    sequences.append(dictOfSeqByCommonNamePlusSuffix[sharVar])
                varID = variables.index(sharVar) + 1
                solution['variableIDs'].add(varID)
    else:
        solution['variableIDs'] = []
    if 'fnames' in groupDescription['rep'].keys():
        solution['keywords'] = groupDescription['rep']['fnames']
    solution['number'] = int(groupDescription['rep']['label'])
    solution['members'] = list(groupDescription['members'])
    solution['phraseIDs'] = list(solution['phraseIDs'])
    solution['variableIDs'] = list(solution['variableIDs'])
    solution['count'] = int(groupDescription['count'])
    # print 'solution ', solution
    solutions.append(solution)

print "Writing solutions"
dumpOutput(solutions, 'solutions.json')
# with open(path.join(destFolder, 'solutions.json'), 'w') as outfh:
    # json.dump(solutions, outfh, sort_keys=True, indent=4, cls=ElenaEncoder)

def generateCodeWithFeatureSpans(phrase):
    # TODO: isn't there a builtin that does this?
    def checkIfAllAlphaNumeric(string):
        for char in string:
            if not char.isalnum():
                return False
        return True

    p2 = re.compile(r'(\W+)')
    splitPhrase = p2.split(phrase)

    newcodeline = ''
    for tok in splitPhrase:
        if checkIfAllAlphaNumeric(tok) and not tok=='':
            newcodeline += "<span class='feature feature-"+ tok +"'>" + tok + "</span>"
        else:
            newcodeline += tok

    return newcodeline

print "Finding most common indent and writing phrases"
for i in range(len(phrases)):
    phrase = phrases[i]
    mostCommonIndent = tabCounter[phrase].most_common(1)[0][0]
    phrases[i] = {'id': i+1, 'code': cgi.escape(phrase), 'indent': mostCommonIndent,'codeWithFeatureSpans':generateCodeWithFeatureSpans(phrase)} #, 'aveLineNum':aveLineNum}

dumpOutput(phrases, 'phrases.json')
# with open(path.join(destFolder, 'phrases.json'), 'w') as outfh:
    # json.dump(phrases, outfh, sort_keys=True, indent=4, cls=ElenaEncoder)

print "Collecting and writing variables"
for i in range(len(variables)):
    variable = variables[i]
    sequence = sequences[i]
    variables[i] = {'id': i+1, 'varName': variable, 'varNameAndSeq': variable + ':'+str(sequence), 'sequence': sequence } #, 'aveLineNum':aveLineNum}

dumpOutput(variables, 'variables.json')
# with open(path.join(destFolder, 'variables.json'), 'w') as outfh:
#     json.dump(variables, outfh, sort_keys=True, indent=4, cls=ElenaEncoder)


'''
print 'other returned: ', otherReturned
print 'total others', len(otherReturned)
otherReturnedCtr = Counter()
otherReturnedCtr.update(otherReturned)
pprint.pprint(otherReturnedCtr)

print 'Check to make sure these numbers are not too high:'
print 'numSkippedSols_1, numSkippedSols_2, numSkippedSols_Tidy'
print numSkippedSols_1, numSkippedSols_2, numSkippedSols_Tidy
print 'numSkippedSols_3 and 4 and 5 and 6', numSkippedSols_3, numSkippedSols_4,numSkippedSols_tooLong, numSkippedSols_6, numSkippedSols_7, numSkippedSols_8

print 'numSkippedSols_2b', numSkippedSols_2b
print 'src_skipped_by_philip', src_skipped_by_philip
print 'solnum_skipped_by_philip', solnum_skipped_by_philip
print 'len', len(solnum_skipped_by_philip), ' set-len ', '''

#print 'len(set(numSkippedSols_1)) ',len(set(numSkippedSols_1))
#print 'len(set(numSkippedSols_2)) ',len(set(numSkippedSols_2))
print 'len(set(numSkippedSols_2b)) ',len(set(numSkippedSols_2b))
print set(numSkippedSols_2b)
#print 'len(set(numSkippedSols_3)) ',len(set(numSkippedSols_3))
#print 'len(set(numSkippedSols_4)) ',len(set(numSkippedSols_4))
print 'len(set(numSkippedSols_tooLong)) ',len(set(numSkippedSols_tooLong))
print set(numSkippedSols_tooLong)
print 'len(set(numSkippedSols_6)) ',len(set(numSkippedSols_6))
print set(numSkippedSols_6)
#print 'len(set(numSkippedSols_7)) ',len(set(numSkippedSols_7))
#print numSkippedSols_7
#print 'len(set(numSkippedSols_8)) ',len(set(numSkippedSols_8))
#print numSkippedSols_8
print 'len(set(numSkippedSols_NoSharedVars)) ',len(set(numSkippedSols_NoSharedVars))
print set(numSkippedSols_NoSharedVars)

print 'len(set(numSkippedSols_commonVarClash)) ',len(set(numSkippedSols_commonVarClash))
print set(numSkippedSols_commonVarClash)

print 'len(set(numSkippedSols_localcommonVarClash)) ',len(set(numSkippedSols_localcommonVarClash))
print set(numSkippedSols_localcommonVarClash)

print 'len(set(numSkippedSols_weirdVarClash)) ',len(set(numSkippedSols_weirdVarClash))
print set(numSkippedSols_weirdVarClash)

print 'len(set(numSkippedSols_Tidy)) ',len(set(numSkippedSols_Tidy))
print set(numSkippedSols_Tidy)
print 'len(set(numSkippedSols_Logger)) ',len(set(numSkippedSols_Logger))
print set(numSkippedSols_Logger)
print 'len(set(solnum_skipped_by_philip)) ',len(set(solnum_skipped_by_philip))
print set(solnum_skipped_by_philip)
print 'len(set(numSkippedSols_RemoveComments)) ',len(set(numSkippedSols_RemoveComments))
print numSkippedSols_RemoveComments


