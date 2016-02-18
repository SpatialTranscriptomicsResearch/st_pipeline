#!/usr/bin/env python
""" 
This module contains some functions and utilities for SAM/BAM files
"""

from stpipeline.common.utils import *
import logging 
import pysam

def sortSamFile(input_sam, outputFolder=None):
    """
    :param input is a SAM/BAM file with mapped reads
    :param outputFolder the location where to place the output file
    It simply sorts a sam/bam file containing mapped reads by position
    """
    
    logger = logging.getLogger("STPipeline")
    logger.info("Start SAM sorting")
    
    sam_type = getExtension(input_sam).lower()
    output_sam = 'mapped_filtered_sorted.' + sam_type
        
    if outputFolder is not None and os.path.isdir(outputFolder):
        output_sam = os.path.join(outputFolder, output_sam)
        
    pysam.sort("-n", "-o", output_sam, "-O", sam_type, "-T", output_sam, input_sam)
    
    if not fileOk(output_sam):
        error = "Error annotating: output file is not present " + output_sam
        logger.error(error)
        raise RuntimeError(error + "\n")
        
    logger.info("Finish SAM sorting")
    return output_sam

def filterMappedReads(mapped_reads, 
                      qa_stats, 
                      hash_reads,
                      min_length=28,
                      outputFolder=None, 
                      keep_discarded_files=False):
    """ 
    :param mapped_reads SAM file obtained from STAR containing the aligmnents
    :param hash_reads a hash table with read names that contain barcode
    :param min_length the min number of mapped bases we enforce in an alignment
    :param outputFolder if we want to specify where to put the output file
    :param keep_discarded_files true if we want to write the un-annotated reads to a file
    Iterate the alignments and discards reads that are secondary or too short.
    It also discards reads that do not contain a mapped barcode.
    It will add the barcode, coordinates and umi as extra tags.
    It assumes all the reads are mapped.
    """
    
    logger = logging.getLogger("STPipeline")
    
    sam_type = getExtension(mapped_reads).lower()
    file_output = 'mapped_filtered.' + sam_type
    file_output_discarded = 'mapped_discarded.' + sam_type
        
    if outputFolder is not None and os.path.isdir(outputFolder):
        file_output = os.path.join(outputFolder, file_output)
        file_output_discarded = os.path.join(outputFolder, file_output_discarded)
    
    flag_read = "rb"
    flag_write = "wb"
    if sam_type == "sam":
        flag_read = "r"
        flag_write = "wh"
        
    infile = pysam.AlignmentFile(mapped_reads, flag_read)
    outfile = pysam.AlignmentFile(file_output, flag_write, template=infile)
    if keep_discarded_files:
        outfile_discarded = pysam.AlignmentFile(file_output_discarded, flag_write, template=infile)
       
    dropped_secondary = 0
    dropped_short = 0
    dropped_barcode = 0
    present = 0

    for sam_record in infile.fetch(until_eof=True):
        present += 1
        discard_read = False
        
        # Add the barcode and coordinates info if present otherwise discard
        try:
            # The probability of a collision is very very low
            key = hash(sam_record.query_name)
            for tag in hash_reads[key]:
                tag_tokens = tag.split(":")
                sam_record.set_tag(tag_tokens[0], tag_tokens[2], tag_tokens[1])
        except KeyError:
            dropped_barcode += 1
            continue
            
        # Get how many bases were mapped
        mapped_bases = 0
        for cigar_tuple in sam_record.cigartuples:
            if cigar_tuple[0] == 0:
                mapped_bases += cigar_tuple[1]
        
        # We need this so we don't duplicate reads
        if not sam_record.is_secondary:
            sam_record.set_tag("NH", None)
            
        # Discard if secondary alignment or only few bases mapped  
        if sam_record.is_secondary:
            dropped_secondary += 1
            discard_read = True
        elif mapped_bases != 0 and mapped_bases < min_length:
            dropped_short += 1
            discard_read = True

        if discard_read:
            if keep_discarded_files:
                outfile_discarded.write(sam_record)
        else:
            outfile.write(sam_record)
                  
    infile.close()
    outfile.close()
    if keep_discarded_files:
        outfile_discarded.close()

    if not fileOk(file_output):
        error = "Error filtering mapped reads: output file is not present " + file_output
        logger.error(error)
        raise RuntimeError(error + "\n")
            
    logger.info("Finish filtering mapped reads, stats:" \
                "\nPresent: " + str(present) + \
                "\nDropped - secondary alignment : " + str(dropped_secondary) + \
                "\nDropped - too short : " + str(dropped_short) + \
                "\nDropped - barcode : " + str(dropped_barcode))  
    
    # Update QA object 
    qa_stats.reads_after_mapping = present - (dropped_secondary + dropped_short)
    return file_output