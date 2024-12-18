import pyroSAR
from pyroSAR.snap.auxil import parse_recipe, parse_node, execute
import os
import glob
import datetime
import pathlib

from .auxils import remove


def S1_coh_proc(
    infiles,
    out_dir="default",
    slice_assembly=False,
    tmpdir=None,
    t_res=20,
    t_crs=32633,
    out_format="GeoTIFF",
    gpt_paras=None,
    pol="full",
    IWs=["IW1", "IW2", "IW3"],
    ext_DEM=False,
    ext_DEM_noDatVal=-9999,
    ext_Dem_file=None,
    msk_noDatVal=False,
    ext_DEM_EGM=True,
    BGC_demResamp="BICUBIC_INTERPOLATION",
    TC_demResamp="BILINEAR_INTERPOLATION",
    osvPath=None,
    cohWinRg=11,
    cohWinAz=3,
    ml_RgLook=4,
    ml_AzLook=1,
    firstBurstIndex=None,
    lastBurstIndex=None,
    clean_tmpdir=True,
    osvFail=False,
    tpm_format="BEAM-DIMAP",
):
    """[S1_InSAR_coh_proc]
    function for processing InSAR coherences from S-1 SLC files in SNAP
    Parameters
    ----------
        infiles: list or str
            filepaths of SLC zip files
        out_dir: str or None
            output folder if None a default folder structure is provided: "COH/pol/"
        tmpdir: str
            temporary dir for intermediate processing steps, its automatically created at cwd if none is provided
        t_res: int, float
            resolution in meters of final product, default is 20
        t_crs: int
            EPSG code of target coordinate system, default is 4326
        out_format: str
            format of final output, formats supported by SNAP, default is GeoTiff
        gpt_paras: none or list
            a list of additional arguments to be passed to the gpt call
        pol: str or list or "full"
            polaristations to process, "full" processes all available polarizations, default is "full"
        IWs: str or list
            selected subswath for processing, default is all 3
        extDEM: bool
            set to true if external DEM should be used in processing
        ext_DEM_noDatVal: int or float
            dependent on external DEM, default False
        ext_DEM_file: str
            path to file of external DEM, must be a format that SNAP can handle
        msk_NoDatVal: bool
            if true No data values of DEM, especially at sea, are masked out
        ext_DEM_EGM: bool
            apply earth gravitational model to external DEM, default true
        imgResamp: str
            image resampling method, must be supported by SNAP
        demResamp: str
            DEM resampling method, must be supported by SNAP
        BCG_demResamp= str
            resampling algorithm of Back Geo-Coding
        TC_demResamp= str
            resampling algorithm of terrain correction
        cohWinRg: int
            size of moving window for coherence estimation in range, default is 11
        cohWinAz: int
            size of moving window for coherence estimation in azimuth, default is 3
        ml_RgLook: int
            number of looks in range, default is 4
        ml_AzLook: int
            number of looks in azimuth, default is 1
        clean_tmpdir, bool
            delete tmpdir, default true
        osvPath: None
            specify path to locally stored OSVs, if none default OSV path of SNAP is set
        tpm_format: str
            specify the SNAP format for temporary files: "BEAM-DIMAP" or "ZNAP". "BEAM-DIMAP" default.
        Returns
        -------
        Raster files of selected output format for selected H-alpha features
        Examples
        --------
        process backscatter intensities VV and VH for given SLC file

        >>> filenames= ['S1B_IW_SLC__1SDV_20201229T170010_20201229T170037_024920_02F722_8B6C.zip.zip', 'S1B_IW_SLC__1SDV_20201217T170011_20201217T170038_024745_02F172_1D38.zip']
        >>> gpt_paras = ["-e", "-x", "-c","35G", "-q", "16", "-J-Xms25G", "-J-Xmx75G"]
        >>> pol= "full"
        >>> S1_InSAR_coh_proc(infiles= filenames, gtp_paras= gpt_paras, pol= "full")
    """
    timea = datetime.datetime.now()
    ##define formatName for reading zip-files
    formatName = "SENTINEL-1"
    ##specifiy ending of tmp-files
    if tpm_format == "ZNAP":
        file_end = ".znap.zip"
    elif tpm_format == "BEAM-DIMAP":
        file_end = ".dim"
    ##list of abbreviated month for creation of source Bands string
    month_list = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    ##queck if at least two files are loaded for coh estiamtion
    if len(infiles) == 1:
        raise RuntimeError("At least 2 scenes needed for coherence estimation")

    ##check if a single IW or consecutive IWs are selected
    if isinstance(IWs, str):
        IWs = [IWs]
    if sorted(IWs) == ["IW1", "IW3"]:
        raise RuntimeError("Please select single or consecutive IW")
    ##extract info about files and order them by date
    info = pyroSAR.identify_many(infiles, sortkey="start")
    ##collect filepaths sorted by date
    fps_lst = []
    for fp in info:
        fp_str = fp.scene
        fps_lst.append(fp_str)

    ##check if all files are of the same relative orbit
    relOrbs = []
    for o in info:
        orb = o.orbitNumber_rel
        relOrbs.append(orb)

    query_orb = relOrbs.count(relOrbs[0]) == len(relOrbs)
    ##raise error if different rel. orbits are detected
    if query_orb is False:
        raise RuntimeError(
            message.format("Files of different relative orbits detected")
        )
    ##query and handle polarisations, raise error if selected polarisations don't match (see Truckenbrodt et al.: pyroSAR: geocode)
    info_ms = info[0]
    orbit = info_ms.orbit

    if isinstance(pol, str):
        if pol == "full":
            pol = info_ms.polarizations
        else:
            if pol in info_ms.polarizations:
                pol = [pol]
            else:
                raise RuntimeError(
                    f"polarization {pol} does not exists in the source product"
                )
    elif isinstance(pol, list):
        pol = [x for x in pol if x in info_ms.polarizations]
    else:
        raise RuntimeError("polarizations must be of type str or list")
    ##specify auto download DEM and handle external DEM file
    if ext_DEM is False:
        demName = "SRTM 1Sec HGT"
        ext_DEM_file = None
    else:
        demName = "External DEM"
    ##raise error if no path to external file is provided
    if ext_DEM is True and ext_DEM_file is None:
        raise RuntimeError("No DEM file provided. Specify path to DEM-file")
    if t_crs == 4326:
        crs = 'GEOGCS["WGS 84", DATUM["WGS_1984", SPHEROID["WGS 84",6378137,298.257223563, AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]], PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
    else:
        crs = f"EPSG:{t_crs}"
    ##check if correct DEM resampling methods are supplied
    reSamp_LookUp = [
        "NEAREST_NEIGHBOUR",
        "BILINEAR_INTERPOLATION",
        "CUBIC_CONVOLUTION",
        "BISINC_5_POINT_INTERPOLATION",
        "BISINC_11_POINT_INTERPOLATION",
        "BISINC_21_POINT_INTERPOLATION",
        "BICUBIC_INTERPOLATION",
    ]

    message = "{0} must be one of the following:\n- {1}"
    if BGC_demResamp not in reSamp_LookUp:
        raise ValueError(
            message.format("demResamplingMethod", "\n- ".join(reSamp_LookUp))
        )
    if TC_demResamp not in reSamp_LookUp:
        raise ValueError(
            message.format("imgResamplingMethod", "\n- ".join(reSamp_LookUp))
        )

    ##query unique dates of files: selection of paired images for coherence estimation
    dates_info = []
    for d in info:
        di = d.start.split("T")[0]
        dates_info.append(di)

    unique_dates_info = list(set(dates_info))
    unique_dates_info = sorted(
        unique_dates_info, key=lambda x: datetime.datetime.strptime(x, "%Y%m%d")
    )
    ##raise error if only one unique date is supplied
    if len(unique_dates_info) == 1:
        raise RuntimeError("Please supply images from 2 different dates")

    ##check for files of the same date and put them in separate lists
    pair_dates_idx = []

    for a in unique_dates_info:
        tmp_dates = []
        for idx, elem in enumerate(dates_info):
            if a == elem:
                tmp_dates.append(idx)

        pair_dates_idx.append(tmp_dates)
    ##selection of paired files for coherence estimation
    for i in range(0, len(pair_dates_idx) - 1):
        fps1 = list(map(fps_lst.__getitem__, pair_dates_idx[i]))
        fps2 = list(map(fps_lst.__getitem__, pair_dates_idx[i + 1]))

        fps_paired = [fps1, fps2]
        info_lst = [pyroSAR.identify(fps1[0]), pyroSAR.identify(fps2[0])]
        ##check availability of orbit state vector file
        orbitType = "Sentinel Precise (Auto Download)"
        match = info_lst[0].getOSV(osvType="POE", returnMatch=True, osvdir=osvPath)
        match2 = info_lst[1].getOSV(osvType="POE", returnMatch=True, osvdir=osvPath)
        if match is None or match2 is None:
            info_lst[0].getOSV(osvType="RES", osvdir=osvPath)
            info_lst[1].getOSV(osvType="RES", osvdir=osvPath)
            orbitType = "Sentinel Restituted (Auto Download)"

        ##build sourceBands string for coherence estimation
        dates = []
        for i in info_lst:
            date = i.start.split("T")[0]
            date_int = int(date[4:6])
            month = month_list[date_int - 1]
            date_tmp = date[6:8] + month + date[0:4]
            dates.append(date_tmp)

        ##extract dates as str from filename for the day and the full datetime
        date1 = info_lst[0].start.split("T")[0]
        date2 = info_lst[1].start.split("T")[0]

        datetime1 = info_lst[0].start
        datetime2 = info_lst[1].start

        date_uniq = [date1, date2]
        graph_dir = f"{tmpdir}/graphs"
        isExist = os.path.exists(graph_dir)
        if not isExist:
            os.makedirs(graph_dir)
        date_uniq = [date1, date2]

        if slice_assembly:
            # manage numbers of scenes needed per time step to estimate coherence, initiate sliceAssembly if necessary
            if len(fps1) == 1 and len(fps2) == 1:
                slcAs_fps_ms = fps1
                slcAs_fps_slv = fps2
            else:
                if len(fps1) == 1 and len(fps2) > 1:
                    slcAs_fps_slv = fps2
                    idx_start = 1
                    idx_stop = len(fps_paired)
                elif len(fps1) > 1 and len(fps2) == 1:
                    slcAs_fps_ms = fps1
                    idx_start = 0
                    idx_stop = len(fps_paired) - 1
                else:
                    idx_start = 0
                    idx_stop = len(fps_paired)

                ## initiate sliceAssembly where the time step consists of more than one scene
                for fp in range(idx_start, idx_stop):
                    if fp == 0:
                        slcAs_name = (f"S1_relOrb_{str(relOrbs[0])}_COH_{date_uniq[fp]}_SLC_slv")
                        slcAs_out = os.path.join(tmpdir, slcAs_name)
                    else:
                        slcAs_name = (f"S1_relOrb_{str(relOrbs[0])}_COH_{date_uniq[fp]}_SLC_ms")
                        slcAs_out = os.path.join(tmpdir, slcAs_name)

                    workflow_slcAs = parse_recipe("blank")

                    read1 = parse_node("Read")
                    read1.parameters["file"] = fps_paired[fp][0]
                    read1.parameters["formatName"] = formatName
                    readers = [read1.id]

                    workflow_slcAs.insert_node(read1)

                    for r in range(1, len(fps_paired[fp])):
                        readn = parse_node("Read")
                        readn.parameters["file"] = fps_paired[fp][r]
                        readn.parameters["formatName"] = formatName
                        workflow_slcAs.insert_node(
                            readn, before=read1.id, resetSuccessorSource=False
                        )
                        readers.append(readn.id)

                    slcAs = parse_node("SliceAssembly")
                    slcAs.parameters["selectedPolarisations"] = pol

                    workflow_slcAs.insert_node(slcAs, before=readers)
                    read1 = slcAs

                    write_slcAs = parse_node("Write")
                    write_slcAs.parameters["file"] = slcAs_out
                    write_slcAs.parameters["formatName"] = tpm_format

                    workflow_slcAs.insert_node(write_slcAs, before=slcAs.id)

                    workflow_slcAs.write(f"{tmpdir}/graphs/Coh_slc_prep_graph")

                    execute(f"{tmpdir}/graphs/Coh_slc_prep_graph.xml", gpt_args=gpt_paras)

                ###import sliceAssemblies according to how many files per time step are needed
                if len(fps1) > 1 and len(fps2) == 1:
                    slcAs_fps_ms = glob.glob(f"{tmpdir}/*_SLC_ms{file_end}")[
                        0
                    ]
                elif len(fps1) == 1 and len(fps2) > 1:
                    slcAs_fps_slv = glob.glob(
                        f"{tmpdir}/*_SLC_slv{file_end}"
                    )[0]
                elif len(fps1) > 1 and len(fps2) > 1:
                    slcAs_fps_slv = glob.glob(
                        f"{tmpdir}/*_SLC_slv{file_end}"
                    )[0]
                    slcAs_fps_ms = glob.glob(f"{tmpdir}/*_SLC_ms{file_end}")[0]
            inFormat = tpm_format
        else:
            slcAs_fps_ms = fps1
            slcAs_fps_slv = fps2
            inFormat = formatName

        print(f"Primary image: {fps1}")
        print(f"Secondary image: {fps2}")
        uid = slcAs_fps_ms.split(".")[-2][-4:] + slcAs_fps_slv.split(".")[-2][-4:]
        out = (
            f"S1_{orbit}_relOrb_{str(relOrbs[0])}_COH_{datetime1}_{datetime2}_{uid}"
        )
        out_folder = f"{out_dir}/{out}"
        isExist = os.path.exists(out_folder)
        if not isExist:
            os.makedirs(out_folder)
        pol_proc = []
        for polar in pol:
            if os.path.isfile(f"{out_folder}/{polar}.tif") is False:
                pol_proc.append(polar)
        if len(pol_proc) > 0:
            pol = pol_proc
            ##start coherence estimation for each IW
            for p in pol:
                print(f"Polarisation: {p}")
                for iw in IWs:
                    print(f"Processing IW: {iw}")
                    out_name = f"S1_relOrb_{str(relOrbs[0])}_{iw}_COH_{p}_{datetime1}_{datetime2}_{uid}_TPD"
                    tmp_out = os.path.join(tmpdir, out_name)

                    ##parse_workflows
                    workflow_coh = parse_recipe("blank")
                    read1 = parse_node("Read")
                    read1.parameters["file"] = slcAs_fps_ms
                    read1.parameters["formatName"] = inFormat
                    workflow_coh.insert_node(read1)

                    aof = parse_node("Apply-Orbit-File")
                    aof.parameters["orbitType"] = orbitType
                    aof.parameters["polyDegree"] = 3
                    aof.parameters["continueOnFail"] = osvFail

                    workflow_coh.insert_node(aof, before=read1.id)

                    ts = parse_node("TOPSAR-Split")
                    ts.parameters["subswath"] = iw
                    ts.parameters["selectedPolarisations"] = p

                    workflow_coh.insert_node(ts, before=aof.id)

                    if isinstance(slcAs_fps_slv, list):
                        query_fps_slv = slcAs_fps_slv[0]
                    else:
                        query_fps_slv = slcAs_fps_slv

                    read2 = parse_node("Read")
                    read2.parameters["file"] = slcAs_fps_slv

                    if pathlib.Path(query_fps_slv).suffix != file_end:
                        read2.parameters["formatName"] = formatName

                    workflow_coh.insert_node(read2)

                    aof2 = parse_node("Apply-Orbit-File")
                    aof2.parameters["orbitType"] = (
                        orbitType  #'Sentinel Restituted (Auto Download)' Sentinel Precise (Auto Download)
                    )
                    aof2.parameters["polyDegree"] = 3
                    aof2.parameters["continueOnFail"] = osvFail

                    workflow_coh.insert_node(aof2, before=read2.id)

                    ts2 = parse_node("TOPSAR-Split")
                    ts2.parameters["subswath"] = iw
                    ts2.parameters["selectedPolarisations"] = p

                    workflow_coh.insert_node(ts2, before=aof2.id)

                    bgc = parse_node("Back-Geocoding")
                    bgc.parameters["demName"] = demName
                    bgc.parameters["demResamplingMethod"] = BGC_demResamp
                    bgc.parameters["externalDEMFile"] = ext_Dem_file
                    bgc.parameters["externalDEMNoDataValue"] = ext_DEM_noDatVal
                    bgc.parameters["resamplingType"] = "BISINC_5_POINT_INTERPOLATION"
                    bgc.parameters["maskOutAreaWithoutElevation"] = msk_noDatVal

                    workflow_coh.insert_node(bgc, before=[ts.id, ts2.id])

                    coh = parse_node("Coherence")
                    coh.parameters["subtractFlatEarthPhase"] = True
                    coh.parameters["singleMaster"] = True
                    coh.parameters["cohWinRg"] = cohWinRg
                    coh.parameters["cohWinAz"] = cohWinAz
                    coh.parameters["demName"] = demName
                    coh.parameters["subtractTopographicPhase"] = True
                    coh.parameters["externalDEMFile"] = ext_Dem_file
                    coh.parameters["externalDEMNoDataValue"] = ext_DEM_noDatVal
                    coh.parameters["externalDEMApplyEGM"] = True

                    workflow_coh.insert_node(coh, before=bgc.id)

                    tpd = parse_node("TOPSAR-Deburst")
                    tpd.parameters["selectedPolarisations"] = p
                    workflow_coh.insert_node(tpd, before=coh.id)

                    write_coh = parse_node("Write")
                    write_coh.parameters["file"] = tmp_out
                    write_coh.parameters["formatName"] = tpm_format

                    workflow_coh.insert_node(write_coh, before=tpd.id)
                    workflow_coh.write(f"{tmpdir}/graphs/Coh_tmp_prep_graph")
                    execute(
                        f"{tmpdir}/graphs/Coh_tmp_prep_graph.xml", gpt_args=gpt_paras
                    )

                tmp_fps = glob.glob(f"{tmpdir}/S1_relOrb_{str(relOrbs[0])}*{p}_{datetime1}_{datetime2}_{uid}_TPD{file_end}")

                if len(IWs) == 1:
                    tpm_source = (
                        f"coh_{IWs[0]}_{p}_{dates[1]}_{dates[0]}"
                    )
                else:
                    tpm_source = f"coh_{p}_{dates[1]}_{dates[0]}"

                out = f"S1_{orbit}_relOrb_{str(relOrbs[0])}_COH__{p}_{datetime1}_{datetime2}_{uid}"
                print(tpm_source)
                isExist = os.path.exists(out_folder)
                if not isExist:
                    os.makedirs(out_folder)

                out_name = ( f"S1_{orbit}_relOrb_{str(relOrbs[0])}_COH__{p}_{datetime1}_{datetime2}_{uid}")
                out_path = os.path.join(out_folder, out_name)

                ##create workflow for merging
                workflow_tpm = parse_recipe("blank")

                read1 = parse_node("Read")
                read1.parameters["file"] = tmp_fps[0]
                workflow_tpm.insert_node(read1)
                ##handling multiple vs single IW
                if len(tmp_fps) > 1:
                    readers = [read1.id]

                    for t in range(1, len(tmp_fps)):
                        readn = parse_node("Read")
                        readn.parameters["file"] = tmp_fps[t]
                        workflow_tpm.insert_node(
                            readn, before=read1.id, resetSuccessorSource=False
                        )
                        readers.append(readn.id)

                    tpm = parse_node("TOPSAR-Merge")
                    tpm.parameters["selectedPolarisations"] = p
                    workflow_tpm.insert_node(tpm, before=readers)
                    last_id = tpm.id
                else:
                    last_id = read1.id

                    ##multi looking for either one IW or multiple ones
                ml = parse_node("Multilook")
                ml.parameters["sourceBands"] = tpm_source
                ml.parameters["nRgLooks"] = ml_RgLook
                ml.parameters["nAzLooks"] = ml_AzLook
                ml.parameters["grSquarePixel"] = True
                ml.parameters["outputIntensity"] = False

                workflow_tpm.insert_node(ml, before=last_id)

                tc = parse_node("Terrain-Correction")
                tc.parameters["sourceBands"] = tpm_source
                tc.parameters["demName"] = demName
                tc.parameters["externalDEMFile"] = ext_Dem_file
                tc.parameters["externalDEMNoDataValue"] = ext_DEM_noDatVal
                tc.parameters["externalDEMApplyEGM"] = ext_DEM_EGM
                tc.parameters["demResamplingMethod"] = TC_demResamp
                tc.parameters["imgResamplingMethod"] = TC_demResamp
                tc.parameters["pixelSpacingInMeter"] = t_res
                tc.parameters["mapProjection"] = crs
                tc.parameters["saveSelectedSourceBand"] = True
                tc.parameters["outputComplex"] = False
                tc.parameters["nodataValueAtSea"] = msk_noDatVal

                workflow_tpm.insert_node(tc, before=ml.id)

                end_name = p
                out_path = os.path.join(out_folder, out_name)
                end_path = os.path.join(out_folder, end_name)

                write_tpm = parse_node("Write")
                write_tpm.parameters["file"] = out_path
                write_tpm.parameters["formatName"] = out_format

                workflow_tpm.insert_node(write_tpm, before=tc.id)

                ##write graph and execute graph
                workflow_tpm.write(f"{tmpdir}/graphs/Coh_TPM_continued_proc_graph")
                # breakpoint()
                execute(
                    f"{tmpdir}/graphs/Coh_TPM_continued_proc_graph.xml",
                    gpt_args=gpt_paras,
                )
                print(f"Write {end_path}")
                os.system(f"rio cogeo create {out_path}.tif {end_path}.tif")
                os.unlink(f"{out_path}.tif")

                timeb = datetime.datetime.now()
                proc_time = timeb - timea
                print(f"Processing time: {proc_time}")

            if clean_tmpdir:
                files = glob.glob(f"{tmpdir}/S1*") + glob.glob(f"{tmpdir}/S1*")
                for fi in files:
                    remove(fi)
            print(f"Processing time: {proc_time}")
        else:
            print(f"{out} already exists")
