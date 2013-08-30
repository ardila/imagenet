"""A module docstring that describes the nature of the data set, the web site that describes the data set more fully,
and contain relevant references to academic literature.

Logic for downloading the data set from the most official internet distribution location possible.
Logic for unpacking and loading that data set into primitive Python data types, if possible."""

from bs4 import BeautifulSoup
from random import sample
import os
from urllib2 import urlopen
import numpy as np
import random
import tarfile
import tabular as tb
import Image
import ImageOps
import skdata.larray as larray
import cPickle
import fnmatch
from collections import defaultdict
import itertools
from dldata import dataset_templates
from joblib import Parallel, delayed
import pwd

main_dir = os.path.expanduser('~/.skdata/imagenet')
username = pwd.getpwuid(os.getuid())[0]
IMG_SOURCE = username + '@mh17.mit.edu:/mindhive/dicarlolab/u/ardila/.skdata/imagenet/images'
default_image_path = os.path.join(main_dir, 'images')
default_meta_path = os.path.join(main_dir, 'meta')


#TODO : deal with username and accesskey so that we can share this code


def download_images_by_synset(synsets, seed=None, num_per_synset='all', firstonly=False, path=None,
                              username='ardila', accesskey='bd662acb4866553500f17babd5992810e0b5a439'):
    """
    Stores a random #num images for synsets specified by synsets from the latest release to path specified
    Since files are stored as tar files online, the entire synset must be downloaded to access random images.

    If 'all' is passed as the num argument, all images are stored.

    If the argument firstonly is set to true, then download times can be reduced by only extracting the first
    few images

    Returns a meta tabarray object containing wnid and filename for each downloaded image
    """
    if path is None:
        path = os.getcwd()
    if not os.path.exists(path):
        os.makedirs(path)
    synsets = list(synsets)
    random.seed(seed)
    kept_names = []
    kept_synset_list = []
    for i, synset in enumerate(synsets):
        synset_names = []
        url = 'http://www.image-net.org/download/synset?' + \
              'wnid=' + str(synset) + \
              '&username=' + username + \
              '&accesskey=' + accesskey + \
              '&release=latest'
        print i
        print url
        url_file = urlopen(url)
        tar_file = tarfile.open(fileobj=url_file, mode='r|')
        if firstonly and not (num_per_synset == 'all'):
            keep_idx = xrange(num_per_synset)
            for tarinfo in tar_file:
                synset_names.append(tarinfo.name)
                tar_file.extract(tarinfo, path)
        else:
            for tarinfo in tar_file:
                synset_names.append(tarinfo.name)
                tar_file.extract(tarinfo, path)
            if num_per_synset == 'all':
                keep_idx = range(len(synset_names))
            else:
                keep_idx = sample(range(len(synset_names)), num_per_synset)
            files_to_remove = frozenset(synset_names) - frozenset([synset_names[idx] for idx in keep_idx])
            for file_to_remove in files_to_remove:
                os.remove(path + '/' + file_to_remove)
        kept_names.extend([synset_names[idx] for idx in keep_idx])
        kept_synset_list.extend([synset] * len(keep_idx))
    meta = tb.tabarray(records=zip(kept_names, kept_synset_list), names=['filename', 'synset'])
    return meta


def download_2013_ILSCRV_synsets(num_per_synset='all', seed=None, path=None, firstonly=False):
    """
    Stores a random #num images for the 2013 ILSCRV synsets from the latest release.
    Since files are stored as tar files online, the entire synset must be downloaded to access random images.

    If 'all' is passed as the num argument, all images are stored.

    If the argument firstonly is set to true, then download times can be reduced by only extracting the first
    few images

    Returns a tabular meta object that has a record for each image containing 2 fields
        synset: the synset of the image
        filename: the filename of the image
    """
    synsets_not_ready_yet = ['n04399382']  # Somehow, teddy bears are not ready for download as of 6/14/2013
    synsets = get2013_Categories()
    synsets = set(synsets) - set(synsets_not_ready_yet)
    return download_images_by_synset(synsets, seed=seed, num_per_synset=num_per_synset, path=path, firstonly=firstonly)


def get2013_Categories():
        """Get list of synsets in 2013 ILSCRV Challenge by scraping the challenge's website"""
        name_list = []
        synset_list = []
        #Grabbed website to extract synsets for all images
        parser = BeautifulSoup(urlopen("http://www.image-net.org/challenges/LSVRC/2013/browse-synsets"))

        def is_a_2013_category(tag):
            """
            Returns true if the tag is a link to a category in the 2013 challenge
            :type tag: tag
            :rtype : boolean
            :param tag: tag object
            """
            if tag.has_attr('href'):
                if 'synset' in tag['href']:
                    return True
            else:
                return False

        linkTags = parser.findAll(is_a_2013_category)
        for linkTag in linkTags:
            name_list.append(linkTag.string)
            link = linkTag['href']
            synset_list.append(link.partition('=')[2])
        return synset_list


def parent_child(synset_list):
        """
        Tests whether synsets in a list overlap in hierarchy.
        Returns true if any synset is a descendant of any other
        synset_list: list of strings (synsets)
        """
        urlbase = 'http://www.image-net.org/api/text/wordnet.structure.hyponym?wnid='
        value = False  # innocent until proven guilty
        for synset in synset_list:
            children = [synset.rstrip().lstrip('-') for synset in urlopen(urlbase+synset).readlines()[1:]]
            if any(child in synset_list for child in children):
                value = True
                break
        return value


def get_full_filename_dictionary():
#This is a (maybe _the_) key piece of metadata, so it is installed to a specific location locally
    filename = 'filenames_dict.p'
    folder = main_dir
    try:
        filenames_dict = cPickle.load(open(os.path.join(folder, filename), 'rb'))
    except IOError:
        print 'Filename dictionary not found, attempting to copy from IMG_SOURCE'
        download_file_to_folder(filename, folder)
        filenames_dict = cPickle.load(open(os.path.join(folder, filename), 'rb'))
    return filenames_dict


def save_filename_dict_from_img_folder(path=None):
    """
    Run this code at IMG_SOURCE to build the dictionary.
    os.listdir is very slow, so allow for about 24hr runtime for large img folders
    """
    if path is None:
        path = os.getcwd()
    filenames_dict = defaultdict(list)
    filenames = os.listdir(path)
    imgs = [f for f in filenames if f.endswith('.JPEG')]
    for f in imgs:
        synset = f.split('_')[0]
        # im_id = f.split('_')[1].rstrip('.JPEG')
        filenames_dict[synset].append(f)
    cPickle.dump(filenames_dict, open('filenames_dict.p', 'wb'))


def get_word_dictionary():
    words_text = urlopen("http://www.image-net.org/archive/words.txt").readlines()
    word_dictionary = {}
    for row in words_text:
        word_dictionary[row.split()[0]] = ' '.join(row.split()[1:]).rstrip('\n')
    return word_dictionary


def get_definition_dictionary():
    gloss_text = urlopen("http://www.image-net.org/archive/gloss.txt").readlines()
    definition_dictionary = {}
    for row in gloss_text:
        definition_dictionary[row.split()[0]] = ' '.join(row.split()[1:]).rstrip('\n')
    return definition_dictionary


def get_tree_structure(synset_list):
    filename = 'full_tree_structure.p'
    folder = main_dir
    try:
        full_tree_structure = cPickle.load(open(os.path.join(folder, filename), 'rb'))
        tree = {synset: full_tree_structure[synset] for synset in synset_list}
    except IOError:
        print "Calculating full tree structure using api"
        urlbase = 'http://www.image-net.org/api/text/wordnet.structure.hyponym?wnid='
        tree = defaultdict(dict)
        # multiple_parents = []
        for i, synset in enumerate(synset_list):
            if i % 100 == 0:
                print float(i)/len(synset_list)
            children = [wnid.rstrip().lstrip('-') for wnid in urlopen(urlbase+synset).readlines()[1:]]
            tree[synset]['children'] = children
            for child in children:
                if tree[child].get('parents') is not None:
                    tree[child]['parents'].append(synset)
                    # multiple_parents.append(child)
                else:
                    tree[child]['parents'] = [synset]
        cPickle.dump(tree, open(os.path.join(folder, filename), 'wb'))
        print 'done'
    return tree


class Imagenet(object):
    def __init__(self,
                 meta_path=default_meta_path,
                 img_path=default_image_path):
        if not os.path.exists(img_path):
            os.makedirs(img_path)
        self.img_path = img_path
        if not os.path.exists(meta_path):
            os.makedirs(meta_path)
        self.meta_path = meta_path
        self.cache = cache(img_path)
        self.default_preproc = {'resize_to': (256, 256), 'mode': 'RGB', 'dtype': 'float32',
                                'crop': None, 'mask': None, 'normalize': True}

    @property
    def meta(self):
        if not hasattr(self, '_meta'):
            self._meta = self._get_meta()
        return self._meta

    @property
    def filenames(self):
        return self.meta['filename']

    def _get_meta(self):
        """Loads the synset meta from file, if it exists.
        If it doesn't exist, calls _get_meta"""
        try:
            tabular_load = tb.io.loadbinary(os.path.join(self.meta_path, 'meta.npz'))
            # This seems like a flaw with tabular's loadbinary.
            meta = tb.tabarray(records=tabular_load[0], dtype=tabular_load[1])
        except IOError:
            print 'Could not load meta from file, constructing'
            s = self.synset_meta
            filenames = list(itertools.chain.from_iterable(
                             [s[synset]['filenames'] for synset in self.synset_meta.keys()]))
            synsets = [filename.split('_')[0] for filename in filenames]
            meta = tb.tabarray(records=zip(filenames, synsets), names=['filename', 'synset'])
            tb.io.savebinary(os.path.join(self.meta_path, 'meta.npz'), meta)
        return meta

    @property
    def synset_meta(self):
        if not hasattr(self, '_synset_meta'):
            self._synset_meta = self._get_synset_meta()
        return self._synset_meta

    def _get_synset_meta(self):
        """Loads the synset meta from file, if it exists.
        If it doesn't exist, calls _get_synset_meta"""
        try:
            synset_meta = cPickle.load(open(os.path.join(self.meta_path, 'synset_meta.p'), 'rb'))
        except IOError:
            print 'Could not load synset meta from file, constructing'
            synset_list = self.get_synset_list()
            words = get_word_dictionary()
            definitions = get_definition_dictionary()
            filenames = self.get_filename_dictionary(synset_list)
            tree_struct = get_tree_structure(synset_list)
            synset_meta = dict([(synset, {'words': words[synset],
                                          'definition': definitions[synset],
                                          'filenames': filenames[synset],
                                          'num_images': len(filenames[synset]),
                                          'parents': tree_struct[synset].get('parents'),
                                          'children': tree_struct[synset].get('children')}) for synset in synset_list])
            cPickle.dump(synset_meta, open(os.path.join(self.meta_path, 'synset_meta.p'), 'wb'))
        return synset_meta

    def get_synset_list(self, thresh=0):
        """
        thresh: int, minimum number of files to be included on the list
        """
        all_synsets_url = 'http://www.image-net.org/api/text/imagenet.synset.obtain_synset_list'
        synsets_list = [wnid.rstrip() for wnid in urlopen(all_synsets_url).readlines()[:-2]]
        if thresh > 0:
            synsets_list = filter(lambda x: self.synset_meta[x]['num_images'] >= thresh, synsets_list)
        return synsets_list

    def get_filename_dictionary(self, synset_list='all'):
        full_dict = get_full_filename_dictionary()
        if synset_list == 'all':
            synset_list = self.get_synset_list()
        return {synset: full_dict[synset] for synset in synset_list}

    def get_images(self, preproc):
        """
        Create a lazily reevaluated array with preprocessing specified by a preprocessing dictionary
        preproc. See the documentation in ImgDownloaderCacherPreprocesser

        """
        file_names = self.meta['filename']
        processor = ImgDownloaderCacherPreprocessor(source=IMG_SOURCE, cache=self.cache, preproc=preproc)
        return larray.lmap(processor,
                           file_names,
                           f_map=processor)

    def get_pixel_features(self, preproc=None):
        preproc['flatten'] = True
        return self.get_images(preproc)


class cache():
    def __init__(self, path, cache_set=None):
        self.path = path
        if cache_set is None:
            try:
                self.set = cPickle.load(open(os.path.join(path, 'cached_set.p'), 'rb'))
            except IOError:
                self.set = set([filename for filename in os.listdir(path) if fnmatch.fnmatch(filename, '*.JPEG')])

    def save(self):
        cPickle.dump(self.set, open(os.path.join(self.path, 'cached_set.p'), 'wb'))

    def download(self, filename, source):
        """
        Downloads the image to the cache
        :param filename: filename of image to download
        :param source: string
        :return: full path
        """
        if filename not in self.set:
            print 'downloading file ' + str(filename)
            download_file_to_folder(filename, self.path, source)
            self.set.add(filename)
            self.save()
        return os.path.join(self.path, filename)


def download_file_to_folder(filename, folder, source=IMG_SOURCE):
    command = 'rsync -az ' + os.path.join(source, filename) + ' ' + folder
    os.system(command)


class ImgDownloaderCacherPreprocessor(dataset_templates.ImageLoaderPreprocesser):
    """
    Class used to lazily downloading images to a cache, evaluating resizing/other pre-processing
    and loading image from file in an larray
    """
    def __init__(self, source, cache, preproc):
        """
        :param source: string, adress passable to rsync where images are located
        :param cache: a cache object with a path and set membership checking
        :param preproc: A preprocessing spec. A preprocessing spec is a dictionary containing:
            resize_to: Image is resized to the tuple given here (note: not reshaped)
            dtype: The datatype of the image array
            mode: 'RGB' or 'L' sepcifies whether or not to store color images
            mask: Image object which is used to mask the image
            crop: array of [minx, maxx, miny, maxy] crop box applied after resize
            normalize: If true, then the image set to zero mean and unit standard deviation

        """
        self.cache = cache
        self.source = source
        self.preproc = preproc
        super(ImgDownloaderCacherPreprocessor, self).__init__(preproc)

    def __call__(self, file_names):
        """
        :param file_names: file_names to download and preprocess
        :return: image
        """
        if isinstance(file_names, str):
            file_names = [file_names]

        file_paths = [self.cache.download(file_name, self.source) for file_name in file_names]
        results = Parallel(n_jobs=-1)(delayed(load_and_process)(file_path, self.preproc) for file_path in file_paths)
        return np.asarray(results)
        # return np.asarray(map(self.load_and_process, np.asarray(file_paths)))


def load_and_process(file_path, preproc):
    processer = dataset_templates.ImageLoaderPreprocesser(preproc)
    return processer(str(file_path))


class Imagenet_synset_subset(Imagenet):

    def __init__(self, synset_list, name, img_path=default_image_path, meta_path=default_meta_path):
        """
        :param synset_list: List of synsets to include in this subset
        :param img_path: Path to image files
        :param name: Unique name for this subset
        """
        self.synset_list = synset_list
        self.name = name
        super(Imagenet_synset_subset, self).__init__(img_path=img_path,
                                                     meta_path=meta_path)

    def get_synset_list(self, thresh=0):
        """
        thresh: int, minimum number of files to be included on the list
        """
        synsets_list = self.synset_list
        if thresh > 0:
            synsets_list = filter(lambda x: self.synset_meta[x]['num_images'] >= thresh, synsets_list)
        return synsets_list


class Imagenet_filename_subset(Imagenet_synset_subset):

    def __init__(self, filenames, name, img_path=default_image_path, meta_path=None):
        self.filename_dict = defaultdict(list)
        synset_list = []
        for f in filenames:
            synset = f.split('_')[0]
            self.filename_dict[synset].append(f)
            if synset not in synset_list:
                synset_list.append(synset)

        self._synset_list = [filename.split('_')[0] for filename in filenames]
        synset_list = list(np.unique(np.array(self._synset_list)))
        super(Imagenet_filename_subset, self).__init__(synset_list, name, img_path, meta_path)

    def get_filename_dictionary(self, synsets=None):
        if synsets is None:
            synsets = self.get_synset_list()
        return {synset: self.filename_dict[synset] for synset in synsets}





