import pyroSAR
from pyroSAR.snap.auxil import parse_recipe, parse_node, execute
import os
import glob
import datetime
from .auxils import remove
# from .auxils import get_burst_geometry, remove


def S1_INT_proc(
    infiles,
    out_dir=None,
    slice_assembly = False,
    tmpdir=None,
    shapefile=None,
    t_res=20,
    t_crs=32633,
    out_format="GeoTIFF",
    gpt_paras=None,
    pol="full",
    IWs=["iw1", "iw2", "iw3"],
    ext_DEM=False,
    ext_DEM_noDatVal=-9999,
    ext_Dem_file=None,
    msk_noDatVal=False,
    ext_DEM_EGM=True,
    imgResamp="BICUBIC_INTERPOLATION",
    demResamp="BILINEAR_INTERPOLATION",
    speckFilter="Boxcar",
    filterSizeX=5,
    filterSizeY=5,
    ml_RgLook=4,
    ml_AzLook=1,
    ref_plain="gamma",
    l2dB_arg=True,
    osvPath=None,
    clean_tmpdir=True,
    osvFail=False,
    tpm_format="BEAM-DIMAP",
):
    """[S1_INT_proc]
    function for processing backscatter intensities VV and VH from S-1 SLC files in SNAP
    Parameters
    ----------
        infiles: list or str
            filepaths of SLC zip files
        out_dir: str or None
            output folder if None a default folder structure is provided: "INT/polarization/"
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
        speckFilter: str
            type of speckle filtering approach, default is Boxcar
        filterSizeX: int
            window size of speckle filter in x, default is 5
        filterSizeY: int
            window size of speckle filter in y, default is 5
        ml_RgLook: int
            number of looks in range, default is 4
        ml_AzLook: int
            number of looks in azimuth, default is 1
        l2dB: bool
            option for conversion from linear to dB scaling of output, default true
        clean_tmpdir, bool
            delete tmpdir, default true
        osvPath: None
            specify path to locally stored OSVs, if none default OSV path of SNAP is set
        tpm_format: str
            specify the SNAP format for temporary files: "BEAM-DIMAP" or "ZNAP". "BEAM-DIMAP" default.
        Returns
        -------
        Raster files of selected output format for selected H-alpha features
        Note
        ----
        Only set first and last burstindex if all files you are processing have the same number of bursts
        Examples
        --------
        process backscatter intensities VV and VH for given SLC file

        >>> filename= 'S1A_IW_GRDH_1SDV_20180829T170656_20180829T170721_023464_028DE0_F7BD.zip'
        >>> gpt_paras = ["-e", "-x", "-c","35G", "-q", "16", "-J-Xms25G", "-J-Xmx75G"]
        >>> pol= "full"
        >>> S1_INT_proc(infiles= filename, gtp_paras= gpt_paras, pol= "full")
    """

    timea = datetime.datetime.now()

    if tpm_format == "ZNAP":
        file_end = ".znap.zip"
    elif tpm_format == "BEAM-DIMAP":
        file_end = ".dim"

   ##extract info about files and order them by date
    ##handle length and type of infiles: str or list
    if isinstance(infiles, str):
        info= pyroSAR.identify(infiles)
        fps_lst=[info.scene]
        info_ms= info
        info= [info]
    elif isinstance(infiles, list):
        info= pyroSAR.identify_many(infiles, sortkey='start')
        ##collect filepaths sorted by date
        fps_lst=[]
        for fp in info:
            fp_str=fp.scene
            fps_lst.append(fp_str)
        info_ms= info[0]
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
    if ext_DEM is False:
        demName = "SRTM 1Sec HGT"
        ext_DEM_file = None
    else:
        demName = "External DEM"
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
    if demResamp not in reSamp_LookUp:
        raise ValueError(
            message.format("demResamplingMethod", "\n- ".join(reSamp_LookUp))
        )
    if imgResamp not in reSamp_LookUp:
        raise ValueError(
            message.format("imgResamplingMethod", "\n- ".join(reSamp_LookUp))
        )
    ##check if correct speckle filter option is supplied
    speckleFilter_options = [
        "Boxcar",
        "Median",
        "Frost",
        "Gamma Map",
        "Refined Lee",
        "Lee",
        "Lee Sigma",
    ]
    if speckFilter not in speckleFilter_options:
        raise ValueError(
            message.format("speckleFilter", "\n- ".join(speckleFilter_options))
        )
    ##query unique dates of files: determine if sliceAssembly is required
    dates_info = []
    for d in info:
        di = d.start.split("T")[0]
        dates_info.append(di)

    unique_dates_info = list(set(dates_info))
    unique_dates_info = sorted(
        unique_dates_info, key=lambda x: datetime.datetime.strptime(x, "%Y%m%d")
    )

    ##check for files of the same date and put them in sublists
    pair_dates_idx = []

    for a in unique_dates_info:
        tmp_dates = []
        for idx, elem in enumerate(dates_info):
            if a == elem:
                tmp_dates.append(idx)

        pair_dates_idx.append(tmp_dates)
    ##selection of paired files for sliceAssembly
    for i in range(0, len(pair_dates_idx)):
        fps_grp = list(map(fps_lst.__getitem__, pair_dates_idx[i]))
        # get relative orbit number of grouped files
        info_tmp = pyroSAR.identify(fps_grp[0])
        relOrb = info_tmp.orbitNumber_rel
        sensor = info_tmp.sensor
        orbit = info_tmp.orbit
        date_str = info_tmp.start

        ##check availability of orbit state vector
        orbitType = "Sentinel Precise (Auto Download)"

        match = info_tmp.getOSV(osvType="POE", returnMatch=True, osvdir=osvPath)
        if match is None:
            info_tmp.getOSV(osvType="RES", osvdir=osvPath)
            orbitType = "Sentinel Restituted (Auto Download)"

        graph_dir = f"{tmpdir}/graphs"
        isExist = os.path.exists(graph_dir)
        if not isExist:
            os.makedirs(graph_dir)
    print(slice_assembly)
    if len(fps_grp) > 1 and slice_assembly == True:

        slcAs_name = f"{sensor}_relOrb_{str(relOrb)}_INT_{unique_dates_info[i]}_slcAs"
        slcAs_out = os.path.join(tmpdir, slcAs_name)

        workflow_slcAs = parse_recipe("blank")
        read1 = parse_node('Read')
        read1.parameters['file'] = fps_grp[0]
        read1.parameters['formatName'] = tpm_format
        readers = [read1.id]

        workflow_slcAs.insert_node(read1)

        for r in range(1, len(fps_grp)):
            readn = parse_node('Read')
            readn.parameters['file'] = fps_grp[r]
            readn.parameters['formatName'] = tpm_format
            workflow_slcAs.insert_node(readn, before = read1.id, resetSuccessorSource=False)
            readers.append(readn.id)

        slcAs = parse_node("SliceAssembly")
        slcAs.parameters["selectedPolarisations"] = pol

        workflow_slcAs.insert_node(slcAs, before = readers)
        read1 = slcAs

        write_slcAs = parse_node("Write")
        write_slcAs.parameters["file"] = slcAs_out
        write_slcAs.parameters["formatName"] = tpm_format

        workflow_slcAs.insert_node(write_slcAs, before= slcAs.id)
        workflow_slcAs.write("INT_slc_prep_graph")

        execute('INT_slc_prep_graph.xml', gpt_args= gpt_paras, outdir= tmpdir)

        scene = slcAs_out + file_end
    ##pass file path if no sliceAssembly required
    else:
        scene = fps_grp[0]

    out = ( f"{sensor}_{orbit}_relOrb_{str(relOrb)}_INT_{date_str}_Orb_Cal_Deb_ML_TF_Spk_TC")
    out_folder = f"{out_dir}/{out}"

    pol_proc = []
    for polar in pol:
        if os.path.exists(f"{out_folder}/{polar}.tif") is False:
            pol_proc.append(polar)
    isExist = os.path.exists(out_folder)
    if not isExist:
        os.makedirs(out_folder)

    if len(pol_proc) > 0:
        pol = pol_proc
        for p in pol:
            print(f"Polariztaion: {p}")
            for iw in IWs:
                print(f"Processing: {iw}")
                tpm_name = (
                    f"{sensor}_{p}_INT_relOrb_{str(relOrb)}_{unique_dates_info[i]}_{iw}_2TPM")
                tpm_out = os.path.join(tmpdir, tpm_name)

                workflow = parse_recipe("blank")
                read = parse_node("Read")
                read.parameters["file"] = scene
                read.parameters["copyMetadata"] = "true"
                workflow.insert_node(read)
                last_node = read.id
                ts1 = parse_node("TOPSAR-Split")
                ts1.parameters["subswath"] = iw
                workflow.insert_node(ts1, before=read.id)
                last_node = ts1.id

                aof = parse_node("Apply-Orbit-File")
                aof.parameters["orbitType"] = orbitType
                aof.parameters["polyDegree"] = 3
                aof.parameters["continueOnFail"] = osvFail
                workflow.insert_node(aof, before=last_node)

                cal = parse_node("Calibration")
                cal.parameters["selectedPolarisations"] = p
                cal.parameters["createBetaBand"] = False
                cal.parameters["outputBetaBand"] = True
                cal.parameters["outputSigmaBand"] = False

                workflow.insert_node(cal, before=aof.id)  #

                tpd = parse_node("TOPSAR-Deburst")
                tpd.parameters["selectedPolarisations"] = p
                workflow.insert_node(tpd, before=cal.id)  #

                write_tmp = parse_node("Write")
                write_tmp.parameters["file"] = tpm_out
                write_tmp.parameters["formatName"] = tpm_format
                workflow.insert_node(write_tmp, before=tpd.id)

                workflow.write(f"{graph_dir}/Int_proc_IW_graph")
                execute(f"{graph_dir}/Int_proc_IW_graph.xml", gpt_args=gpt_paras)

            tpm_in = glob.glob(f"{tmpdir}/{sensor}_{p}_INT_relOrb_{str(relOrb)}_{unique_dates_info[i]}*_2TPM{file_end}")

            if len(IWs) == 1:
                ref = dict()
                ref["beta"] = [f"Beta0_{IWs[0]}_{p}"]
                ref["gamma"] = [f"Gamma0_{IWs[0]}_{p}"]
                ref["sigma"] = [f"Sigma0_{IWs[0]}_{p}"]
            else:
                ref = dict()
                ref["beta"] = [f"Beta0_{p}"]
                ref["gamma"] = [f"Gamma0_{p}"]
                ref["sigma"] = [f"Sigma0_{p}"]
            if ref_plain == "gamma":
                ref_pl_ml = ref["beta"]
                ref_pl = ref["gamma"]
            elif ref_plain == "sigma":
                ref_pl_ml = ref["beta"]
                ref_pl = ref["sigma"]

            workflow = parse_recipe("blank")
            read1 = parse_node("Read")
            read1.parameters["file"] = tpm_in[0]
            read.parameters["formatName"] = tpm_format
            workflow.insert_node(read1)
            last_node = read1.id
            if len(tpm_in) > 1:
                readers = [read1.id]  #

                for t in range(1, len(tpm_in)):
                    readn = parse_node("Read")
                    readn.parameters["file"] = tpm_in[t]
                    read.parameters["formatName"] = tpm_format
                    workflow.insert_node(
                        readn, before=last_node, resetSuccessorSource=False
                    )
                    readers.append(readn.id)  #

                ##TOPSAR merge
                tpm = parse_node("TOPSAR-Merge")
                tpm.parameters["selectedPolarisations"] = p
                workflow.insert_node(tpm, before=readers)
                last_node = tpm.id

            ##multi looking
            ml = parse_node("Multilook")
            ml.parameters["sourceBands"] = ref_pl_ml
            ml.parameters["nRgLooks"] = ml_RgLook
            ml.parameters["nAzLooks"] = ml_AzLook
            ml.parameters["grSquarePixel"] = True
            ml.parameters["outputIntensity"] = False
            workflow.insert_node(ml, before=last_node)
            last_node = ml.id  #

            ##terrain flattening
            tf = parse_node("Terrain-Flattening")
            tf.parameters["sourceBands"] = ref_pl_ml
            tf.parameters["demName"] = demName
            tf.parameters["demResamplingMethod"] = demResamp
            tf.parameters["externalDEMFile"] = ext_Dem_file
            tf.parameters["externalDEMNoDataValue"] = ext_DEM_noDatVal
            tf.parameters["externalDEMApplyEGM"] = True
            tf.parameters["additionalOverlap"] = 0.1
            tf.parameters["oversamplingMultiple"] = 1.0
            if ref_plain == "sigma":
                tf.parameters["outputSigma0"] = True

            workflow.insert_node(tf, before=last_node)
            # speckle filtering
            sf = parse_node("Speckle-Filter")
            sf.parameters["sourceBands"] = ref_pl
            sf.parameters["filter"] = speckFilter
            sf.parameters["filterSizeX"] = filterSizeX
            sf.parameters["filterSizeY"] = filterSizeY

            workflow.insert_node(sf, before=tf.id)
            # terrain correction
            tc = parse_node("Terrain-Correction")
            tc.parameters["sourceBands"] = ref_pl
            tc.parameters["demName"] = demName
            tc.parameters["externalDEMFile"] = ext_Dem_file
            tc.parameters["externalDEMNoDataValue"] = ext_DEM_noDatVal
            tc.parameters["externalDEMApplyEGM"] = ext_DEM_EGM
            tc.parameters["imgResamplingMethod"] = imgResamp
            tc.parameters["demResamplingMethod"] = demResamp
            tc.parameters["pixelSpacingInMeter"] = t_res
            tc.parameters["mapProjection"] = crs
            tc.parameters["saveSelectedSourceBand"] = True
            tc.parameters["nodataValueAtSea"] = msk_noDatVal

            workflow.insert_node(tc, before=sf.id)
            last_node = tc.id

            out = f"{sensor}_{orbit}_relOrb_{str(relOrb)}_INT_{date_str}_Orb_Cal_Deb_ML_TF_Spk_TC"
            out_folder = f"{out_dir}/{out}"
            isExist = os.path.exists(out_folder)
            if not isExist:
                os.makedirs(out_folder)
            out_name = ( f"{sensor}_{orbit}_relOrb_{str(relOrb)}_INT_{p}_{date_str}_Orb_Cal_Deb_ML_TF_Spk_TC" )
            end_name = p

            ##conversion from linear to dB if selected
            if l2dB_arg is True:
                l2DB = parse_node("LinearToFromdB")
                l2DB.parameters["sourceBands"] = ref_pl
                workflow.insert_node(l2DB, before=last_node)
                last_node = l2DB.id
                ##change output name to reflect dB conversion
                out_name = f"{out_name}_dB"

            out_path = os.path.join(out_folder, out_name)
            end_path = os.path.join(out_folder, end_name)
            print(f"GPT: {out_path}")
            write_tpm = parse_node("Write")
            write_tpm.parameters["file"] = out_path
            write_tpm.parameters["formatName"] = out_format
            workflow.insert_node(write_tpm, before=last_node)
            workflow.write(f"{graph_dir}/Int_TPM_continued_proc_graph")
            execute(
                f"{graph_dir}/Int_TPM_continued_proc_graph.xml", gpt_args=gpt_paras
            )  #

            os.system(f"rio cogeo create {out_path}.tif {end_path}.tif")
            os.unlink(f"{out_path}.tif")

        if clean_tmpdir:
            files = glob.glob(f"{tmpdir}/S1*") + glob.glob(f"{tmpdir}/S1*")
            for fi in files:
                remove(fi)

        timeb = datetime.datetime.now()
        proc_time = timeb - timea
        print(f"Processing time: {proc_time}")
    else:
        print(f"{out} already exists")
