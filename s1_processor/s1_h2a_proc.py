import pyroSAR
from pyroSAR.snap.auxil import parse_recipe, parse_node, execute
import os
import glob
import datetime
import shutil

from .auxils import remove


def S1_HA_proc(
    infiles,
    out_dir=None,
    tmpdir=None,
    shapefile=None,
    t_res=20,
    t_crs=4326,
    out_format="GeoTIFF",
    gpt_paras=None,
    IWs=["IW1", "IW2", "IW3"],
    decompFeats=["Alpha", "Entropy", "Anisotropy"],
    ext_DEM=False,
    ext_DEM_noDatVal=-9999,
    ext_Dem_file=None,
    msk_noDatVal=False,
    ext_DEM_EGM=True,
    imgResamp="BICUBIC_INTERPOLATION",
    demResamp="BILINEAR_INTERPOLATION",
    decomp_win_size=5,
    speckFilter="Box Car Filter",
    ml_RgLook=4,
    ml_AzLook=1,
    osvPath=None,
    tpm_format="BEAM-DIMAP",
    clean_tmpdir=True,
    osvFail=False,
):
    """[S1_HA_proc]
    function for processing H-alpha features (Alpha, Entropy, Anisotropy) from S-1 SLC files in SNAP
    Parameters
    ----------
        infiles: list or str
            filepaths of SLC zip files
        out_dir: str or None
            output folder if None a default folder structure is provided: "INT/decompFeat/"
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
        decompFeats: list of str
            containing H/a decompostion features: Alpha, Entropy and Anisotropy
        decomp_win_size: int
            size of moving window in H/a decomposition in pixel, default is 5
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
            type of speckle filtering approach, default is Box Car Filter
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
        Note
        ----
        Only set first and last burstindex if all files you are processing have the same number of bursts
        Examples
        --------
        process all H-alpha features for given SLC file

        >>> filename= 'S1A_IW_GRDH_1SDV_20180829T170656_20180829T170721_023464_028DE0_F7BD.zip'
        >>> gpt_paras = ["-e", "-x", "-c","35G", "-q", "16", "-J-Xms25G", "-J-Xmx75G"]
        >>> decompFeats= ["Alpha", "Entropy", "Anisotropy"]
        >>> S1_HA_proc(infiles= filename, gtp_paras= gpt_paras, decompFeats= decompFeats)
    """

    ##define formatName for reading zip-files
    ##specify ending of tmp-files
    if tpm_format == "ZNAP":
        file_end = ".znap.zip"
    elif tpm_format == "BEAM-DIMAP":
        file_end = ".dim"
    ##check if a single IW or consecutive IWs are selected
    if isinstance(IWs, str):
        IWs = [IWs]
    if sorted(IWs) == ["IW1", "IW3"]:
        raise RuntimeError("Please select single or consecutive IW")

    ##extract info about files and order them by date
    ##handle length and type of infiles: str or list
    if isinstance(infiles, str):
        info = pyroSAR.identify(infiles)
        fps_lst = [info.scene]
        info = [info]
    elif isinstance(infiles, list):
        info = pyroSAR.identify_many(infiles, sortkey="start")
        ##collect filepaths sorted by date
        fps_lst = []
        for fp in info:
            fp_str = fp.scene
            fps_lst.append(fp_str)

    else:
        raise RuntimeError("Please provide str or list of filepaths")
    ##query and handle polarisations, raise error if selected polarisations don't match (see Truckenbrodt et al.: pyroSAR: geocode)
    ##specify auto download DEM and handle external DEM file
    if ext_DEM is False:
        demName = "SRTM 1Sec HGT"
        ext_DEM_file = None
    else:
        demName = "External DEM"
    ##raise error if no path to external file is provided
    if ext_DEM is True and ext_DEM_file is None:
        raise RuntimeError("No DEM file provided. Specify path to DEM-file")
    ##raise error ifwrong decomp feature
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
        "Box Car Filter",
        "IDAN Filter",
        "Refined Lee Filter",
        "Improved Lee Sigma Filter",
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
        pol = info_tmp.polarizations
        date_str = info_tmp.start

        ##check availability of orbit state vector
        orbitType = "Sentinel Precise (Auto Download)"

        match = info_tmp.getOSV(osvType="POE", returnMatch=True, osvdir=osvPath)
        if match is None:
            info_tmp.getOSV(osvType="RES", osvdir=osvPath)
            orbitType = "Sentinel Restituted (Auto Download)"
        ##exception handling of SNAP errors
        # try:
        timea = datetime.datetime.now()
        # slcAs_name= sensor +"_relOrb_"+ str(relOrb)+"_HA_"+unique_dates_info[i]+"_slcAs"
        out = f"{sensor}_{orbit}_relOrb_{str(relOrb)}_HA_{date_str}"
        out_folder = f"{out_dir}/{out}"
        graph_dir = f"{tmpdir}/graphs"
        isExist = os.path.exists(graph_dir)
        if not isExist:
            os.makedirs(graph_dir)

        isExist = os.path.exists(out_folder)
        if not isExist:
            os.makedirs(out_folder)

        feat_proc = []
        for feat in decompFeats:
            if os.path.isfile(f"{out_folder}/{feat}.tif") is False:
                feat_proc.append(feat)

        if os.path.exists(f"{out_folder}/manifest.safe") is False:
            print(f"Copy: {infiles}/manifest.safe to {out_folder}/manifest.safe")
            shutil.copyfile(f"{infiles}/manifest.safe", f"{out_folder}/manifest.safe")

        if os.path.exists(f"{out_folder}/annotation") is False:
            print(f"Copy: {infiles}/annotations to {out_folder}/annotations")
            shutil.copytree(f"{infiles}/annotation", f"{out_folder}/annotation")

        HA_proc_in = infiles
        if len(feat_proc) >= 0:
            for iw in IWs:
                print(f"IW : {iw}")
                tpm_name = (
                    f"{sensor}_HA_relOrb_{str(relOrb)}_{unique_dates_info[i]}_{iw}_2TPM"
                )
                tpm_out = os.path.join(tmpdir, tpm_name)
                ##generate workflow for IW splits
                workflow = parse_recipe("blank")

                read = parse_node("Read")
                read.parameters["file"] = HA_proc_in
                workflow.insert_node(read)

                aof = parse_node("Apply-Orbit-File")
                aof.parameters["orbitType"] = orbitType
                aof.parameters["polyDegree"] = 3
                aof.parameters["continueOnFail"] = osvFail
                workflow.insert_node(aof, before=read.id)
                ##TOPSAR split node
                ts = parse_node("TOPSAR-Split")
                ts.parameters["subswath"] = iw
                workflow.insert_node(ts, before=aof.id)

                cal = parse_node("Calibration")
                cal.parameters["selectedPolarisations"] = pol
                cal.parameters["createBetaBand"] = False
                cal.parameters["outputBetaBand"] = False
                cal.parameters["outputSigmaBand"] = True
                cal.parameters["outputImageInComplex"] = True
                workflow.insert_node(cal, before=ts.id)

                tpd = parse_node("TOPSAR-Deburst")
                tpd.parameters["selectedPolarisations"] = pol
                workflow.insert_node(tpd, before=cal.id)

                write_tmp = parse_node("Write")
                write_tmp.parameters["file"] = tpm_out
                write_tmp.parameters["formatName"] = tpm_format
                workflow.insert_node(write_tmp, before=tpd.id)

                workflow.write("HA_proc_IW_graph")

                execute("HA_proc_IW_graph.xml", gpt_args=gpt_paras)

            for dc in feat_proc:
                print(dc)
                end_name = dc
                dc_label = dc.upper()[0:3]
                ##load temporary files
                tpm_in = glob.glob(
                    tmpdir
                    + "/"
                    + sensor
                    + "_HA_relOrb_"
                    + str(relOrb)
                    + "_"
                    + unique_dates_info[i]
                    + "*_2TPM"
                    + file_end
                )
                ## parse_workflow of INT processing
                workflow_tpm = parse_recipe("blank")

                read1 = parse_node("Read")
                read1.parameters["file"] = tpm_in[0]
                workflow_tpm.insert_node(read1)
                last_node = read1.id
                ##merge IWs if multiple IWs were selected
                if len(tpm_in) > 1:
                    readers = [read1.id]

                    for t in range(1, len(tpm_in)):
                        readn = parse_node("Read")
                        readn.parameters["file"] = tpm_in[t]
                        workflow_tpm.insert_node(
                            readn, before=last_node, resetSuccessorSource=False
                        )
                        readers.append(readn.id)
                    ##TOPSAR merge
                    tpm = parse_node("TOPSAR-Merge")
                    tpm.parameters["selectedPolarisations"] = pol
                    workflow_tpm.insert_node(tpm, before=readers)
                    last_node = tpm.id

                ##create C2 covariance matrix
                polMat = parse_node("Polarimetric-Matrices")
                polMat.parameters["matrix"] = "C2"
                workflow_tpm.insert_node(polMat, before=last_node)
                last_node = polMat.id

                ##multi looking
                ml = parse_node("Multilook")
                ml.parameters["sourceBands"] = ["C11", "C12_real", "C12_imag", "C22"]
                ml.parameters["nRgLooks"] = ml_RgLook
                ml.parameters["nAzLooks"] = ml_AzLook
                ml.parameters["grSquarePixel"] = True
                ml.parameters["outputIntensity"] = False
                workflow_tpm.insert_node(ml, before=last_node)
                last_node = ml.id

                ##polaricmetric speckle filtering
                polSpec = parse_node("Polarimetric-Speckle-Filter")
                polSpec.parameters["filter"] = speckFilter
                workflow_tpm.insert_node(polSpec, before=last_node)
                last_node = polSpec.id

                ##dual-pol H/a decomposition
                polDecp = parse_node("Polarimetric-Decomposition")
                polDecp.parameters["decomposition"] = "H-Alpha Dual Pol Decomposition"
                polDecp.parameters["windowSize"] = decomp_win_size
                polDecp.parameters["outputHAAlpha"] = True

                workflow_tpm.insert_node(polDecp, before=last_node)
                last_node = polDecp.id

                # terrain correction
                # print(f'CRS: {t_crs}')
                tc = parse_node("Terrain-Correction")
                tc.parameters["sourceBands"] = [dc]
                tc.parameters["demName"] = demName
                tc.parameters["externalDEMFile"] = ext_Dem_file
                tc.parameters["externalDEMNoDataValue"] = ext_DEM_noDatVal
                tc.parameters["externalDEMApplyEGM"] = ext_DEM_EGM
                tc.parameters["imgResamplingMethod"] = imgResamp
                tc.parameters["demResamplingMethod"] = demResamp
                tc.parameters["pixelSpacingInMeter"] = t_res
                tc.parameters["mapProjection"] = crs
                tc.parameters["saveSelectedSourceBand"] = True
                # tc.parameters["outputComplex"]= False
                tc.parameters["nodataValueAtSea"] = msk_noDatVal

                workflow_tpm.insert_node(tc, before=last_node)
                last_node = tc.id

                out_name = (
                    sensor
                    + "_"
                    + orbit
                    + "_relOrb_"
                    + str(relOrb)
                    + "_HA_"
                    + dc_label
                    + "_"
                    + date_str
                    + "_Orb_Cal_Deb_ML_Spk_TC"
                )
                out_path = os.path.join(out_folder, out_name)

                out_path = os.path.join(out_folder, out_name)
                end_path = os.path.join(out_folder, end_name)

                write_tpm = parse_node("Write")
                write_tpm.parameters["file"] = out_path
                write_tpm.parameters["formatName"] = out_format
                workflow_tpm.insert_node(write_tpm, before=last_node)

                ##write graph and execute it
                workflow_tpm.write(f"{graph_dir}/HA_TPM_continued_proc_graph")
                execute(
                    f"{graph_dir}/HA_TPM_continued_proc_graph.xml", gpt_args=gpt_paras
                )

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
            print("File already exists")
